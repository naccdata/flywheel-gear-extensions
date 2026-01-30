"""Tests curator.scheduling."""

from datetime import date
from typing import Optional

from curator.scheduling_models import FileModel


def fm(
    filename: str,
    visit_date: Optional[date] = None,
    study_date: Optional[date] = None,
    scan_date: Optional[date] = None,
    scandate: Optional[date] = None,
    scandt: Optional[date] = None,
    img_study_date: Optional[date] = None,
) -> FileModel:
    """Generates a file model for testing, may need to specify dates."""
    return FileModel(
        filename=filename,
        file_id="dummy-file",
        acquisition_id="dummy-acquisition",
        subject_id="dummy-subject",
        modified_date=date.today(),
        visit_date=visit_date,
        study_date=study_date,
        scan_date=scan_date,
        scandate=scandate,
        scandt=scandt,
        img_study_date=img_study_date,
    )


# pylint: disable=(no-self-use)
class TestFileModel:
    """Tests the FileModel Pydantic model."""

    def test_visit_pass(self):
        """Test the visit_pass property works as expected."""
        # pass3
        assert fm("NACCXXX_historic_apoe_genotype.json").visit_pass == "pass3"

        # pass2
        assert fm("NACCXXX_NP-RECORD-2012-02-10_NP.json").visit_pass == "pass2"
        assert fm("NACCXXX_MDS-RECORD-2006-03-23_MDS.json").visit_pass == "pass2"
        assert fm("NACCXXX_MILESTONE-2011-10-26_MLST.json").visit_pass == "pass2"
        assert fm("NACCXXX_FORMS-VISIT-2_MEDS.json").visit_pass == "pass2"
        assert fm("NACCXXX_FORMS-VISIT-3_FTLD.json").visit_pass == "pass2"
        assert fm("NACCXXX_FORMS-VISIT-4_LBD.json").visit_pass == "pass2"

        assert fm("NACCXXX_apoe_genotype.json").visit_pass == "pass2"
        assert fm("NACCXXX_niagads_availability.json").visit_pass == "pass2"

        assert fm("NACCXXX_NCRAD-SAMPLES-BRAIN-2008-06-20.json").visit_pass == "pass2"
        assert (
            fm("NACCXXX_NCRAD-SAMPLES-BRAIN-TISSUE-2008-06-20.json").visit_pass
            == "pass2"
        )
        assert fm("NACCXXX_NCRAD-SAMPLES-BLOOD-2008-06-20.json").visit_pass == "pass2"
        assert fm("NACCXXX_NCRAD-SAMPLES-PLASMA-2008-06-20.json").visit_pass == "pass2"
        assert fm("NACCXXX_NCRAD-SAMPLES-DNA-2008-06-20.json").visit_pass == "pass2"

        assert fm("NACCXXX-SCAN-MR-QC-2023-08-25.json").visit_pass == "pass2"
        assert fm("NACCXXX-SCAN-MR-SBM-2023-08-25.json").visit_pass == "pass2"
        assert fm("NACCXXX-SCAN-PET-QC-2024-08-06.json").visit_pass == "pass2"
        assert (
            fm("NACCXXX-SCAN-AMYLOID-PET-GAAIN-2024-08-06.json").visit_pass == "pass2"
        )
        assert (
            fm("NACCXXX-SCAN-AMYLOID-PET-NPDKA-2024-08-06.json").visit_pass == "pass2"
        )
        assert fm("NACCXXX-SCAN-FDG-PET-NPDKA-2024-08-10.json").visit_pass == "pass2"
        assert fm("NACCXXX-SCAN-TAU-PET-NPDKA-2024-08-27.json").visit_pass == "pass2"

        # pass1
        assert fm("NACCXXX_FORMS-VISIT-5_UDS.json").visit_pass == "pass1"

        # pass 0; covid and cls
        assert fm("NACCXXX_CLS-RECORD-2012-02-10_CLS.json").visit_pass == "pass0"
        assert fm("NACCXXX_CLS-RECORD-2021-01-29_COVID.json").visit_pass == "pass0"

        # pass 0 - lots of different filenames for dicom/niftis
        assert fm("NACCXXX_MR-20250101_2-MPRAGE.dicom.zip").visit_pass == "pass0"
        assert fm("NACCXXX_MR-20250101112428_2-MPRAGE.nii.gz").visit_pass == "pass0"
        assert fm("NACCXXX_MR-20250101_6-AxialPD-T2TSE.dicom.zip").visit_pass == "pass0"
        assert (
            fm("NACCXXX_MR-20250101112428_6-Axial_PD-T2_TSE.nii.gz").visit_pass
            == "pass0"
        )
        assert fm("NACCXXX_MR-20250101_3-MPRAGERepeat.dicom.zip").visit_pass == "pass0"
        assert (
            fm("NACCXXX_MR-20250101112428_3-MPRAGE_Repeat.nii.gz").visit_pass == "pass0"
        )
        assert fm("NACCXXX-MRI-SUMMARY-DATA-2025-1-2.json").visit_pass == "pass0"
        assert fm("NACCXXX-MRI-SUMMARY-DATA-2025-01-12.json").visit_pass == "pass0"

        # invalid/unknown pass
        assert fm("invalid.json").visit_pass is None
