from typing import List, Optional

from curator.compute import (
    MissingTransformError,
    SymbolTable,
    TransformDispatch,
)
from curator.curator import AttributeCondition, ComputeDefinition


class DummyTransforms(TransformDispatch):

    def dummy(self) -> None:
        return None

    def first(self, value_list: List[str]) -> Optional[str]:
        if not value_list:
            return None

        return value_list[0]


class TestTransforms:

    def test_missing(self):
        transforms = DummyTransforms()
        try:
            transforms.evaluate(
                rule=ComputeDefinition(compute='junk_transform', arguments={}))
            raise AssertionError()
        except MissingTransformError as error:
            assert str(
                error
            ) == "'DummyTransforms' object has no attribute 'junk_transform'"

    def test_dummy_call(self):
        transforms = DummyTransforms()
        assert transforms.evaluate(
            rule=ComputeDefinition(compute='dummy', arguments={})) is None

    def test_first_call(self):
        transforms = DummyTransforms()
        assert transforms.evaluate(rule=ComputeDefinition(
            compute='first', arguments={'value_list': ['1', '2']})) == '1'


class TestBuiltins:

    def test_apply(self):
        dispatch = TransformDispatch(SymbolTable({'alpha': 1}))
        assert dispatch.evaluate(
            rule=ComputeDefinition(compute='apply',
                                   arguments={
                                       'attribute': 'alpha',
                                       'mapping': {
                                           1: 'one',
                                           2: 'two'
                                       },
                                       'undefined': 'no value'
                                   })) == 'one'

        dispatch = TransformDispatch(SymbolTable({}))
        assert dispatch.evaluate(
            rule=ComputeDefinition(compute='apply',
                                   arguments={
                                       'attribute': 'alpha',
                                       'mapping': {
                                           1: 'one',
                                           2: 'two'
                                       },
                                       'undefined': 'no value'
                                   })) is None

        dispatch = TransformDispatch(SymbolTable({'alpha': 99}))
        assert dispatch.evaluate(
            rule=ComputeDefinition(compute='apply',
                                   arguments={
                                       'attribute': 'alpha',
                                       'mapping': {
                                           1: 'one',
                                           2: 'two'
                                       },
                                       'undefined': 'no value'
                                   })) == 'no value'

    def test_first_non_null(self):
        dispatch = TransformDispatch(SymbolTable({'alpha': 'a', 'beta': 'b'}))
        assert dispatch.evaluate(rule=ComputeDefinition(
            compute='first_non_null',
            arguments={'attributes': ['alpha', 'beta']})) == 'a'

        dispatch = TransformDispatch(SymbolTable({'alpha': None, 'beta': 'b'}))
        assert dispatch.evaluate(rule=ComputeDefinition(
            compute='first_non_null',
            arguments={'attributes': ['alpha', 'beta']})) == 'b'

        dispatch = TransformDispatch(SymbolTable({'beta': 'b'}))
        assert dispatch.evaluate(rule=ComputeDefinition(
            compute='first_non_null',
            arguments={'attributes': ['alpha', 'beta']})) == 'b'

    def test_create_object(self):
        dispatch = TransformDispatch(SymbolTable({'alpha': 'a', 'beta': 'b'}))
        assert dispatch.evaluate(rule=ComputeDefinition(
            compute='create_object',
            arguments={'attributes': {
                'first': 'alpha',
                'second': 'beta'
            }})) == {
                'first': 'a',
                'second': 'b'
            }

    def test_is_form(self):
        symbol_map = {}
        dispatch = TransformDispatch(SymbolTable(symbol_map))
        assert not dispatch.evaluate(predicate=AttributeCondition(
            predicate='is_form'))

        symbol_map = {'forms': {'json': {'module': 'uds', 'formver': '3.0'}}}
        dispatch = TransformDispatch(SymbolTable(symbol_map))
        assert dispatch.evaluate(predicate=AttributeCondition(
            predicate='is_form'))

        assert dispatch.evaluate(predicate=AttributeCondition(
            predicate='is_form', arguments={'name': 'UDS'}))

        assert dispatch.evaluate(predicate=AttributeCondition(
            predicate='is_form', arguments={
                'name': 'UDS',
                'version': '3.0'
            }))

        assert not dispatch.evaluate(predicate=AttributeCondition(
            predicate='is_form', arguments={
                'name': 'UDS',
                'version': '1.0'
            }))
