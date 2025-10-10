"""Tests preprocessing helpers."""

from typing import Optional, Tuple

from configs.ingest_configs import ModuleConfigs
from keys.keys import DefaultValues, FieldNames, SysErrorCodes
from nacc_common.error_models import CSVLocation
from outputs.error_writer import ListErrorWriter
from outputs.errors import preprocess_errors
from preprocess.preprocessor_helpers import (
    FormPreprocessorErrorHandler,
    PreprocessingContext,
)


class TestFormPreprocessorErrorHandler:
    """Tests the error handles."""

    def __create_error_handler(
        self,
        module: str,
        module_configs: ModuleConfigs,
    ) -> Tuple[FormPreprocessorErrorHandler, ListErrorWriter]:
        """Create an error handler with a ListErrorWriter for testing.

        Args:
            module: module to test
            module_config: corresponding ModuleConfigs to use
        Returns:
            FormPreprocessorErrorHandler: the handler object to test
            ListErrorWriter: error writer to inspect for testing
        """
        error_writer = ListErrorWriter(container_id="dummy", fw_path="dummy/dummy")
        handler = FormPreprocessorErrorHandler(
            module=module, module_configs=module_configs, error_writer=error_writer
        )

        return handler, error_writer

    def __check_error(
        self,
        error_writer: ListErrorWriter,
        pp_context: PreprocessingContext,
        value: str,
        location: str,
        error_code: str,
        message: Optional[str] = None,
    ):
        """Most tests check the same thing, so generalize."""
        assert len(error_writer.errors()) == 1
        file_error = error_writer.errors()[0]
        input_record = pp_context.input_record

        if not message:
            message = preprocess_errors[error_code]

        assert file_error.value == value
        assert file_error.location == CSVLocation(line=1, column_name=location)
        assert file_error.error_type == "error"
        assert file_error.error_code == error_code
        assert file_error.message == message
        assert file_error.ptid == input_record[FieldNames.PTID]
        assert file_error.visitnum == input_record[FieldNames.VISITNUM]
        assert file_error.date == input_record[FieldNames.DATE_COLUMN]
        assert file_error.naccid == input_record[FieldNames.NACCID]

    def test_write_packet_error(self, uds_module_configs, uds_pp_context):
        """Test writing a packet error."""
        handler, error_writer = self.__create_error_handler(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        error_code = SysErrorCodes.INVALID_PACKET
        handler.write_packet_error(uds_pp_context, error_code)

        input_record = uds_pp_context.input_record
        self.__check_error(
            error_writer,
            uds_pp_context,
            input_record[FieldNames.PACKET],
            FieldNames.PACKET,
            error_code,
        )

    def test_write_module_error(self, uds_module_configs, uds_pp_context):
        """Test writing a module error."""
        handler, error_writer = self.__create_error_handler(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        error_code = SysErrorCodes.INVALID_MODULE
        handler.write_module_error(uds_pp_context, error_code)

        self.__check_error(
            error_writer,
            uds_pp_context,
            DefaultValues.UDS_MODULE,
            FieldNames.MODULE,
            error_code,
        )

    def test_write_module_error_custom_message(
        self, uds_module_configs, uds_pp_context
    ):
        """Test writing a module error with custom error code/messsage."""
        handler, error_writer = self.__create_error_handler(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        error_code = "dummy-error"
        message = "dummy-message"
        handler.write_module_error(uds_pp_context, error_code, message=message)

        self.__check_error(
            error_writer,
            uds_pp_context,
            DefaultValues.UDS_MODULE,
            FieldNames.MODULE,
            error_code,
            message=message,
        )

    def test_write_visitnum_error(self, uds_module_configs, uds_pp_context):
        """Test writing a visitnum error."""
        handler, error_writer = self.__create_error_handler(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        error_code = SysErrorCodes.DIFF_VISITNUM
        handler.write_visitnum_error(uds_pp_context, error_code)

        input_record = uds_pp_context.input_record
        self.__check_error(
            error_writer,
            uds_pp_context,
            input_record[FieldNames.VISITNUM],
            FieldNames.VISITNUM,
            error_code,
        )

    def test_write_formver_error(self, uds_module_configs, uds_pp_context):
        """Test writing a formver error."""
        handler, error_writer = self.__create_error_handler(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        error_code = SysErrorCodes.INVALID_VERSION
        handler.write_formver_error(uds_pp_context, error_code)

        input_record = uds_pp_context.input_record
        self.__check_error(
            error_writer,
            uds_pp_context,
            input_record[FieldNames.FORMVER],
            FieldNames.FORMVER,
            error_code,
        )

    def test_write_date_error(self, uds_module_configs, uds_pp_context):
        """Test writing a date error - default date."""
        handler, error_writer = self.__create_error_handler(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        error_code = SysErrorCodes.DIFF_VISITDATE
        handler.write_date_error(uds_pp_context, error_code)

        input_record = uds_pp_context.input_record
        self.__check_error(
            error_writer,
            uds_pp_context,
            input_record[FieldNames.DATE_COLUMN],
            FieldNames.DATE_COLUMN,
            error_code,
        )

    def test_write_date_error_other_date_field(
        self, uds_module_configs, uds_pp_context
    ):
        """Test writing a date error - some other date field."""
        handler, error_writer = self.__create_error_handler(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        input_record = uds_pp_context.input_record
        date_field = "npdodyr"
        input_record[date_field] = "1990"

        error_code = SysErrorCodes.DIFF_VISITDATE
        handler.write_date_error(uds_pp_context, error_code, date_field=date_field)

        self.__check_error(
            error_writer,
            uds_pp_context,
            input_record[date_field],
            date_field,
            error_code,
        )

    def test_write_custom_error_with_args(self, uds_module_configs, uds_pp_context):
        """Test writing a custom error with extra args."""
        handler, error_writer = self.__create_error_handler(
            DefaultValues.UDS_MODULE, uds_module_configs
        )

        input_record = uds_pp_context.input_record
        field = "MODExx"
        input_record[field] = "dummy-mode"

        error_code = SysErrorCodes.MISSING_SUBMISSION_STATUS
        handler.write_preprocessing_error(
            field=field,
            value=input_record[field],
            pp_context=uds_pp_context,
            error_code=error_code,
            extra_args=["mode1", "mode2", "mode3"],
        )

        self.__check_error(
            error_writer,
            uds_pp_context,
            input_record[field],
            field,
            error_code,
            message=(
                "Missing submission status (MODE<form name>) variables "
                "['mode1', 'mode2', 'mode3'] for one or more optional forms"
            ),
        )
