"""Models to handle FW's datasets.

FW has its own fw-dataset library; however this library
causes a lot of package versioning conflicts and is also
a bit overkill for what we generally need, so using our
own version here.
"""

import json
import logging

from datetime import datetime
from pydantic import BaseModel
from typing import Literal, Optional

from s3.s3_bucket import S3BucketInterface

log = logging.getLogger(__name__)

DATASET_DATE_FMT = "%Y-%m-%dT%H:%M:%S.%f%z"


class FWDatasetError(Exception):
	pass


class FWDataset(BaseModel):
    """Models the FW Dataset metadata."""

    bucket: str
    prefix: str
    storage_id: str
    storage_label: Optional[str]
    type: Literal["s3"]  # other types allowed but we only work with S3

    @property
    def full_uri(self) -> str:
    	"""Return the full S3 URI."""
    	return f"{self.bucket}/{self.prefix}"

    def get_latest_version(
    	self, s3_interface: Optional[S3BucketInterface] = None
    ) -> Optional[str]:
    	"""Get latest dataset version under this dataset.

		Args:
			s3_interface: An already-existing S3 interface (optional)
		Returns:
			Prefix of the latest dataset version, if found
    	"""
    	if s3_interface:
    		# just make sure this intereface is compatible with this dataset
    		if s3_interface.bucket_name != self.bucket:
    			raise FWDatasetError(
    				f"Passed s3_interface bucket '{s3_interface.bucket}'"
    				+ f"does not match current dataset bucket '{self.bucket}'")
    	else:
    		s3_interface = S3BucketInterface.create_from_environment(self.bucket)

    	target_path = "/provenance/dataset_description.json"
    	latest_creation = None
    	latest_dataset = None

        try:
            # iterate over the description JSONs to get the creation dates
            found_descriptions = s3_interface.list_directory(
            	self.prefix, glob=f"*{target_path}"
            )

            for file in found_descriptions:
            	with s3_interface.read_data(file) as fh:
            		description = json.load(fh)

                    created = datetime.strptime(
                        description["created"], DATASET_DATE_FMT
                    )
                    if not latest_creation or latest_creation < created:
                        latest_creation = created
                        latest_dataset = file.path

        except Exception as e:
            raise FWDatasetError(f"Failed to inspect '{file.path}': {e}") from e

        if latest_dataset:
            # remove target_path suffix to get prefix of version itself
            latest_dataset = latest_dataset.removesuffix(target_path)
            log.info(f"Found latest dataset: {latest_dataset}")

        return latest_dataset
