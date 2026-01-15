"""Tests for curator.curator."""

from curator.curator import determine_scope


# pylint: disable=(no-self-use)
class TestDetermineScope:
    """Tests the determine_scope method."""

    def test_forms(self):
        """Test form files."""
        assert determine_scope("NACCXXX_CLS-RECORD-2012-02-10_CLS.json") == "cls"
        assert determine_scope("NACCXXX_NP-RECORD-2012-02-10_NP.json") == "np"
        assert determine_scope("NACCXXX_MDS-RECORD-2006-03-23_MDS.json") == "mds"
        assert determine_scope("NACCXXX_MILESTONE-2011-10-26_MLST.json") == "milestone"
        assert determine_scope("NACCXXX_FORMS-VISIT-2_MEDS.json") == "meds"
        assert determine_scope("NACCXXX_FORMS-VISIT-3_FTLD.json") == "ftld"
        assert determine_scope("NACCXXX_FORMS-VISIT-4_LBD.json") == "lbd"
        assert determine_scope("NACCXXX_FORMS-VISIT-5_UDS.json") == "uds"

    def test_genetics(self):
        """Test general genetics files."""
        assert determine_scope("NACCXXX_historic_apoe_genotype.json") == "historic_apoe"
        assert determine_scope("NACCXXX_apoe_genotype.json") == "apoe"
        assert (
            determine_scope("NACCXXX_niagads_availability.json")
            == "niagads_availability"
        )

        # dummy cases for APOE
        assert determine_scope("NACCXXX_historical_apoe_genotype.json") == "apoe"
        assert determine_scope("apoe_historic_genotype.json") is None

    def test_ncrad_biosamples(self):
        """Test NCRAD samples, which can have different sample types."""
        assert (
            determine_scope("NACCXXX_NCRAD-SAMPLES-BRAIN-2008-06-20.json")
            == "ncrad_biosamples"
        )
        assert (
            determine_scope("NACCXXX_NCRAD-SAMPLES-BRAIN-TISSUE-2008-06-20.json")
            == "ncrad_biosamples"
        )
        assert (
            determine_scope("NACCXXX_NCRAD-SAMPLES-BLOOD-2008-06-20.json")
            == "ncrad_biosamples"
        )
        assert (
            determine_scope("NACCXXX_NCRAD-SAMPLES-PLASMA-2008-06-20.json")
            == "ncrad_biosamples"
        )
        assert (
            determine_scope("NACCXXX_NCRAD-SAMPLES-DNA-2008-06-20.json")
            == "ncrad_biosamples"
        )

    def test_scan(self):
        """Test SCAN files."""
        assert determine_scope("NACCXXX-SCAN-MR-QC-2023-08-25.json") == "scan_mri_qc"
        assert determine_scope("NACCXXX-SCAN-MR-SBM-2023-08-25.json") == "scan_mri_sbm"
        assert determine_scope("NACCXXX-SCAN-PET-QC-2024-08-06.json") == "scan_pet_qc"
        assert (
            determine_scope("NACCXXX-SCAN-AMYLOID-PET-GAAIN-2024-08-06.json")
            == "scan_amyloid_pet_gaain"
        )
        assert (
            determine_scope("NACCXXX-SCAN-AMYLOID-PET-NPDKA-2024-08-06.json")
            == "scan_amyloid_pet_npdka"
        )
        assert (
            determine_scope("NACCXXX-SCAN-FDG-PET-NPDKA-2024-08-10.json")
            == "scan_fdg_pet_npdka"
        )
        assert (
            determine_scope("NACCXXX-SCAN-TAU-PET-NPDKA-2024-08-27.json")
            == "scan_tau_pet_npdka"
        )

    def test_unknown(self):
        """Test unknown/invalid files."""
        assert determine_scope("invalid.json") is None
        assert determine_scope("UDS_extra.json") is None
