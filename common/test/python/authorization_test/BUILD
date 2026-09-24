python_tests(
    name="tests",
    dependencies=[":contract_model", ":test_utils"],
)

python_test_utils(
    name="test_utils",
    sources=["conftest.py", "contract.py"],
    dependencies=[":contract_model"],
)

resource(
    name="contract_model",
    source="contract_model.json",
)
