"""Tests curator.scheduling."""

from datetime import date
from typing import Optional

from curator.scheduling_models import FileModel


def fm(
    filename: str,
    visit_date: Optional[str] = None,
    study_date: Optional[str] = None,
    scan_date: Optional[str] = None,
    scandate: Optional[str] = None,
    scandt: Optional[str] = None,
    img_study_date: Optional[str] = None,
) -> FileModel:
    """Generates a file model for testing, may need to specify dates."""
    file_info = {
        "forms": {
            "json": {
                "visitdate": visit_date,
            }
        },
        "raw": {
            "study_date": study_date,
            "scan_date": scan_date,
            "scandate": scandate,
            "scandt": scandt,
        },
        "header": {"dicom": {"StudyDate": img_study_date}},
    }

    return FileModel(
        filename=filename,
        file_id="dummy-file",
        file_info=file_info,
        file_tags=[],
        modified_date=date.today(),
    )


# pylint: disable=(no-self-use)
class TestFileModel:
    """Tests the FileModel Pydantic model."""

    def test_dates(self):
        """Test dates are set correctly."""
        file_model = fm(
            "NACCXXX_FORMS-VISIT-1_UDS.json",
            visit_date="1990-01-01",
            study_date="1991-02-02",
            scan_date="1992-03-03",
            scandate="1993-04-04",
            scandt="1994-05-05",
            img_study_date="1995-06-06",
        )
        assert file_model.visit_date == date(1990, 1, 1)
        assert file_model.study_date == date(1991, 2, 2)
        assert file_model.scan_date == date(1992, 3, 3)
        assert file_model.scandate == date(1993, 4, 4)
        assert file_model.scandt == date(1994, 5, 5)
        assert file_model.img_study_date == date(1995, 6, 6)

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


# pylint: disable=(no-self-use)
class TestDetermineScope:
    """Tests the fm method."""

    def test_forms(self):
        """Test form files."""
        assert fm("NACCXXX_CLS-RECORD-2012-02-10_CLS.json").scope == "cls"
        assert fm("NACCXXX_NP-RECORD-2012-02-10_NP.json").scope == "np"
        assert fm("NACCXXX_MDS-RECORD-2006-03-23_MDS.json").scope == "mds"
        assert fm("NACCXXX_MILESTONE-2011-10-26_MLST.json").scope == "milestone"
        assert fm("NACCXXX_FORMS-VISIT-2_MEDS.json").scope == "meds"
        assert fm("NACCXXX_FORMS-VISIT-3_FTLD.json").scope == "ftld"
        assert fm("NACCXXX_FORMS-VISIT-4_LBD.json").scope == "lbd"
        assert fm("NACCXXX_FORMS-VISIT-5_UDS.json").scope == "uds"

    def test_genetics(self):
        """Test general genetics files."""
        assert fm("NACCXXX_historic_apoe_genotype.json").scope == "historic_apoe"
        assert fm("NACCXXX_apoe_genotype.json").scope == "apoe"
        assert fm("NACCXXX_niagads_availability.json").scope == "niagads_availability"

        # dummy cases for APOE
        assert fm("NACCXXX_historical_apoe_genotype.json").scope == "apoe"
        assert fm("apoe_historic_genotype.json").scope is None

    def test_ncrad_biosamples(self):
        """Test NCRAD samples, which can have different sample types."""
        assert (
            fm("NACCXXX_NCRAD-SAMPLES-BRAIN-2008-06-20.json").scope
            == "ncrad_biosamples"
        )
        assert (
            fm("NACCXXX_NCRAD-SAMPLES-BRAIN-TISSUE-2008-06-20.json").scope
            == "ncrad_biosamples"
        )
        assert (
            fm("NACCXXX_NCRAD-SAMPLES-BLOOD-2008-06-20.json").scope
            == "ncrad_biosamples"
        )
        assert (
            fm("NACCXXX_NCRAD-SAMPLES-PLASMA-2008-06-20.json").scope
            == "ncrad_biosamples"
        )
        assert (
            fm("NACCXXX_NCRAD-SAMPLES-DNA-2008-06-20.json").scope == "ncrad_biosamples"
        )

    def test_scan(self):
        """Test SCAN files."""
        assert fm("NACCXXX-SCAN-MR-QC-2023-08-25.json").scope == "scan_mri_qc"
        assert fm("NACCXXX-SCAN-MR-SBM-2023-08-25.json").scope == "scan_mri_sbm"
        assert fm("NACCXXX-SCAN-PET-QC-2024-08-06.json").scope == "scan_pet_qc"
        assert (
            fm("NACCXXX-SCAN-AMYLOID-PET-GAAIN-2024-08-06.json").scope
            == "scan_amyloid_pet_gaain"
        )
        assert (
            fm("NACCXXX-SCAN-AMYLOID-PET-NPDKA-2024-08-06.json").scope
            == "scan_amyloid_pet_npdka"
        )
        assert (
            fm("NACCXXX-SCAN-FDG-PET-NPDKA-2024-08-10.json").scope
            == "scan_fdg_pet_npdka"
        )
        assert (
            fm("NACCXXX-SCAN-TAU-PET-NPDKA-2024-08-27.json").scope
            == "scan_tau_pet_npdka"
        )

    def test_unknown(self):
        """Test unknown/invalid files."""
        assert fm("invalid.json").scope is None
        assert fm("UDS_extra.json").scope is None
