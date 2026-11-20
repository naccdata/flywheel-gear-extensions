# MRI Reface

Wraps [mri_reface 0.3.5](https://www.nitrc.org/projects/mri_reface) (Christopher G. Schwarz, Mayo Clinic) to de-identify head scans. The face is replaced with a population-average face, which protects against face recognition while changing brain measurements less than defacing.

> mri_reface is free for **non-commercial research use only**. Keep that in mind before uploading the gear to a shared or commercial Flywheel site.

The original gear wrapper was written by R. Ward (University of Wisconsin) and adapted to this repository's conventions.

## Workflow

For the `input_file`, the gear:

1. Stages the input in the form mri_reface reads:
    - `.nii.gz` is decompressed to `.nii` (mri_reface cannot read `.gz`).
    - A DICOM zip is flattened into one directory of `.dcm` files, skipping OS junk (`__MACOSX`, dotfiles), `DICOMDIR`, and `.txt`/`.json`/`.xml` side files.
    - File names are simplified (periods and spaces become dashes), as recommended on the mri_reface forum, because mri_reface parses names on periods.
2. Runs `<mri_reface launcher> <input> <outdir> -imType <im_type> [extra_args]`, with `TMPDIR` set to the job's work directory.
3. Copies the results to the output directory: DICOM output is zipped, the NIfTI is gzipped (if `gzip_nifti`), renders are kept, and registration by-products are dropped unless `save_transforms` is on.

The launcher is auto-detected (`run_mri_reface`, `run_mri_reface.sh`, or `mri_reface` on `PATH` or under common install directories), and the MATLAB Runtime root is appended when a `run_<app>.sh` launcher expects it. If detection picks the wrong command, set `REFACE_COMMAND` in [main.py](../../gear/mri_reface/src/python/mri_reface_app/main.py).

## Inputs

| Input | Base | Description |
| ----- | ---- | ----------- |
| `api-key` | api-key | Read-only; the gear does not modify Flywheel containers. |
| `input_file` | file | A NIfTI (`.nii` or `.nii.gz`) or a zip of DICOM files from a **single series** (`.dicom.zip` / `.zip`). |

## Configuration

Gear configs are defined in [manifest.json](../../gear/mri_reface/src/docker/manifest.json).

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `im_type` | `T1` | Passed to `-imType`. MRI/CT values: `T1`, `T2`, `FLAIR`, `T2st`, `ASL`, `CT`. Empty lets mri_reface decide (the author strongly recommends setting it, especially for DICOM input). |
| `gzip_nifti` | `true` | Save the refaced NIfTI as `.nii.gz`. |
| `save_transforms` | `false` | Keep the registration files (`*_to_MCALT_*Affine.txt`, `*Warp.nii`). |
| `extra_args` | `""` | Extra mri_reface flags, passed through as-is. |
| `debug` | `false` | Log extra detail (detected command, environment, all files produced). |

## Outputs

| Input type | Outputs |
| ---------- | ------- |
| NIfTI | `<name>_deFaced.nii.gz`, before/after render(s) |
| DICOM zip | `<name>_deFaced.dicom.zip`, `<name>_deFaced.nii.gz`, render(s) |

## Building

Unlike other gears in this repository, the image is built on the mri_reface Docker image from NITRC, which is not on a public registry. The Dockerfile adds Python 3.12 (via `uv`) so the gear's pex can run.

1. Download `mri_reface_0.3.5_docker.zip` from NITRC, unzip it, and load or build the image as its instructions say. It is named `mri_reface`. Pin it:

    ```bash
    docker tag mri_reface:latest mri_reface:0.3.5
    ```

2. Check the container user. The Dockerfile assumes `reface-user`:

    ```bash
    docker inspect --format '{{.Config.User}}' mri_reface:0.3.5
    ```

    If it differs, change the `REFACE_USER` default in the [Dockerfile](../../gear/mri_reface/src/docker/Dockerfile).

3. Build and upload as described in the [Gear Development Guide](../development/index.md). The base image must be in the local Docker daemon when running `pants package`.

The manifest `environment` mirrors the base image's `ENV` (MATLAB Runtime paths, `PATH`, `LD_LIBRARY_PATH`), because Flywheel runs the gear with the manifest environment. If the base image changes, update it from `docker inspect --format '{{json .Config.Env}}' mri_reface:0.3.5`.

## Notes

- **Resources:** mri_reface runs ANTs nonlinear registration. Expect several minutes to tens of minutes per scan, and request at least 4 GB RAM for the gear.
- **DICOM input:** the zip must hold one series only. The author does not recommend the direct-DICOM workflow for PET, because it does not correct for motion between frames; convert PET to NIfTI first.
- **Citation:** Schwarz et al., NeuroImage 2021 and 2023 (doi:10.1016/j.neuroimage.2023.120199).
