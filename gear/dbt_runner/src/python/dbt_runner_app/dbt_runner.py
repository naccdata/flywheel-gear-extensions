"""Runs DBT."""

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import List

from gear_execution.gear_execution import (
    GearExecutionError,
)
from s3.s3_bucket import S3BucketInterface

log = logging.getLogger(__name__)


class DBTRunner:
    def __init__(self, project_root: Path) -> None:
        self.__project_root = project_root
        self.__target_dir = project_root / "target"

    def __create_model_output_directories(self) -> None:
        """Create output directories for models with external materialization.

        Scans dbt model files for location configurations and creates
        necessary subdirectories to prevent "directory does not exist"
        errors.
        """
        models_dir = self.__project_root / "models"
        if not models_dir.exists():
            return

        # Pattern to match location in config blocks
        location_pattern = re.compile(r"location\s*=\s*['\"]([^'\"]+)['\"]")

        log.info("Scanning model files for output locations")
        locations_found = set()

        # Recursively find all .sql files
        for sql_file in models_dir.rglob("*.sql"):
            try:
                with open(sql_file, "r") as f:
                    content = f.read()

                # Find all location configurations
                matches = location_pattern.findall(content)
                for location in matches:
                    locations_found.add(location)

            except Exception as e:
                log.debug(f"Could not read {sql_file}: {e}")

        # Create parent directories for all locations
        for location in locations_found:
            location_path = Path(location)
            if not location_path.is_absolute():
                # Resolve relative to project root
                location_path = self.__project_root / location_path

            # Create parent directory
            parent_dir = location_path.parent
            if parent_dir != self.__project_root and not parent_dir.is_dir():
                parent_dir.mkdir(parents=True, exist_ok=True)
                log.info(
                    "Created output directory: "
                    + f"{parent_dir.relative_to(self.__project_root)}"
                )

    def run(self) -> None:
        """Execute dbt run command.

        Raises:
            subprocess.CalledProcessError: If dbt command fails
        Returns:
            True if ran successfullyl, false otherwise
        """
        log.info(f"Running dbt from: {self.__project_root}")

        # Change to project directory
        original_dir = Path.cwd()
        os.chdir(self.__project_root)
        result = None

        try:
            # Ensure target directory exists
            self.__target_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"Ensured target directory exists: {self.__target_dir}")

            # Create subdirectories for model outputs
            self.__create_model_output_directories()

            # Run dbt debug first to check configuration
            log.info("Running dbt debug to verify configuration")
            result = subprocess.run(
                ["dbt", "debug"], capture_output=True, text=True, check=False
            )
            log.info(f"dbt debug output:\n{result.stdout}")
            if result.returncode != 0:
                log.warning(f"dbt debug had warnings:\n{result.stderr}")

            # Run dbt run
            log.info("Running dbt run")
            result = subprocess.run(
                ["dbt", "run"], capture_output=True, text=True, check=True
            )

            # Log output
            log.info(f"dbt run output:\n{result.stdout}")
            if result.stderr:
                log.error(f"dbt run stderr:\n{result.stderr}")

        except subprocess.CalledProcessError as e:
            log.error(f"dbt failed with a return code of {e.returncode}")
            log.error(e.output)
            raise GearExecutionError(e) from e

        finally:
            # Always change back to original directory
            os.chdir(original_dir)

    def __parse_external_models_from_manifest(self) -> List[dict]:
        """Parse manifest.json to extract external model configurations.

        Returns:
            List of dicts with 'name' and 'location' keys for external models
        """
        manifest_path = self.__target_dir / "manifest.json"

        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)

            log.info("Reading manifest.json to find external model outputs")
            nodes = manifest.get("nodes", {})
            external_models = []

            for node_data in nodes.values():
                if (
                    node_data.get("resource_type") == "model"
                    and node_data.get("config", {}).get("materialized") == "external"
                ):
                    location = node_data.get("config", {}).get("location")
                    if location:
                        external_models.append(
                            {"name": node_data.get("name"), "location": location}
                        )

            log.info(f"Found {len(external_models)} external models in manifest")
            return external_models

        except FileNotFoundError:
            log.warning(f"manifest.json not found at {manifest_path}")
        except json.JSONDecodeError as e:
            log.warning(f"Failed to parse manifest.json: {e}")
        except Exception as e:
            log.warning(f"Error reading manifest.json: {e}")

        return []

    def __resolve_model_path(self, location: str) -> Path:
        """Resolve model location to an absolute path.

        Args:
            location: Location from manifest (relative or absolute)

        Returns:
            Absolute path to the model output
        """
        if Path(location).is_absolute():
            return Path(location)
        return self.__project_root / location

    def __find_external_model_outputs(self) -> List[Path]:
        """Find all external model outputs by reading manifest.json.

        This function reads the dbt manifest to find models with external
        materialization and returns paths to their output files.

        Returns:
            List of paths to parquet files created by external models
        """
        parquet_files = []

        # Parse external models from manifest
        external_models = self.__parse_external_models_from_manifest()

        # Convert locations to absolute paths and verify they exist
        for model in external_models:
            parquet_path = self.__resolve_model_path(model["location"])

            if parquet_path.exists():
                parquet_files.append(parquet_path)
                log.info(
                    f"Found external model output: {model['name']} at {parquet_path}"
                )
            else:
                log.warning(
                    f"External model {model['name']} location not found: {parquet_path}"
                )

        # Fallback: recursively find all parquet files under target/
        if not parquet_files:
            log.info(
                "Falling back to recursive parquet file search in target directory"
            )
            for parquet_file in self.__target_dir.rglob("*.parquet"):
                if not parquet_file.name.endswith(".duckdb"):
                    parquet_files.append(parquet_file)
                    log.info(f"Found parquet file: {parquet_file}")

        return parquet_files

    def upload_external_model_outputs(
        self,
        s3_interface: S3BucketInterface,
        output_prefix: str,
    ) -> None:
        """Upload external model outputs to storage preserving subdirectory
        structure.

        Args:
            s3_interface: S3BucketInterface instance for uploads
            output_prefix: Path prefix in storage where files will be written
        """
        parquet_files = self.__find_external_model_outputs()
        log.info(f"Uploading model outputs to {output_prefix}")

        if parquet_files:
            log.info(f"Found {len(parquet_files)} parquet file(s) to upload")
            for parquet_file in parquet_files:
                # Calculate relative path to preserve subdirectory structure
                try:
                    # Try to get path relative to target directory
                    relative_path = str(parquet_file.relative_to(self.__target_dir))
                except ValueError:
                    # If file is not under target dir, use relative to project root
                    try:
                        relative_path = str(
                            parquet_file.relative_to(self.__project_root)
                        )
                    except ValueError:
                        # Fallback to just the filename
                        relative_path = parquet_file.name

                log.info(f"Uploading {relative_path} to external storage")
                s3_interface.upload_file(parquet_file, output_prefix, relative_path)
        else:
            log.warning("No external model outputs found to upload")

    def save_dbt_artifacts(self, gear_output_dir: Path) -> None:
        """Save dbt artifacts to gear output directory.

        Args:
            gear_output_dir: Gear output directory
        """
        log.info("Saving dbt artifacts to gear outputs")

        gear_output_path = Path(gear_output_dir)
        gear_output_path.mkdir(parents=True, exist_ok=True)

        # List of artifacts to save
        artifacts = [
            "manifest.json",
            "run_results.json",
            "sources.json",
            "compiled",
        ]

        for artifact in artifacts:
            artifact_path = self.__target_dir / artifact

            if artifact_path.exists():
                dest_path = gear_output_path / artifact

                if artifact_path.is_dir():
                    # Copy directory
                    shutil.copytree(artifact_path, dest_path, dirs_exist_ok=True)
                    log.info(f"Saved artifact directory: {artifact}")
                else:
                    # Copy file
                    shutil.copy2(artifact_path, dest_path)
                    log.info(f"Saved artifact: {artifact}")
            else:
                log.debug(f"Artifact not found (skipping): {artifact}")

        log.info("dbt artifacts saved successfully")
