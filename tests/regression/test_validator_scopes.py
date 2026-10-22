"""Regression coverage: validator scopes. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B33StrictValidatorTests(unittest.TestCase):
    def assertAccepted(self, source, candidate):
        from formatter import validate_sql_unchanged
        validate_sql_unchanged(source, candidate)

    def assertRejected(self, source, candidate):
        from formatter import validate_sql_unchanged
        with self.assertRaises(ValueError):
            validate_sql_unchanged(source, candidate)

    def test_only_ast_clause_headers_can_be_uppercased(self):
        source = "select distinct Id as Alias from MixedTable where Id in ('select FROM WHERE');"
        self.assertAccepted(source, source)
        self.assertAccepted(source, source.replace('select distinct', 'SELECT distinct')
                            .replace('from MixedTable', 'FROM MixedTable').replace('where Id', 'WHERE Id'))
        for old, new in (('distinct', 'DISTINCT'), (' as ', ' AS '), (' in ', ' IN ')):
            with self.subTest(old=old):
                self.assertAccepted(source, source.replace(old, new))
        for old, new in (('Id', 'ID'), ('Alias', 'ALIAS'), ('MixedTable', 'MIXEDTABLE'),
                         ("'select FROM WHERE'", "'SELECT FROM WHERE'")):
            with self.subTest(old=old):
                self.assertRejected(source, source.replace(old, new))
        self.assertRejected('SELECT id FROM t;', 'select id FROM t;')
        self.assertRejected('sEleCt id FROM t;', 'Select id FROM t;')
        self.assertRejected('SEL id FROM t;', 'SELECT id FROM t;')
        self.assertRejected('SELECT "where" FROM t;', 'SELECT "WHERE" FROM t;')
        self.assertRejected('SELECT id FROM t -- where\n;', 'SELECT id FROM t -- WHERE\n;')

    def test_tokens_order_types_and_clause_ownership_remain_strict(self):
        source = 'SELECT id FROM t WHERE a=1 AND b=2;'
        for candidate in (
                'SELECT id FROM t HAVING a=1 AND b=2;',
                'SELECT id FROM t WHERE b=2 AND a=1;',
                'SELECT id FROM t WHERE a=1 OR b=2;',
                'SELECT id FROM t WHERE a=1;',
                "SELECT id FROM t WHERE a='1' AND b=2;",
                'SELECT id FROM t WHERE 2=2 AND a=1 AND b=2;',
                'SELECT id FROM t WHERE 1=1 AND a=1 AND b=3;'):
            with self.subTest(candidate=candidate):
                self.assertRejected(source, candidate)

    def test_exact_prefix_allowed_for_eligible_where_only(self):
        for expression in ('a=1 AND b=2', "a=1 AND (b='x' OR b='y')",
                           'a BETWEEN 1 AND 2 AND b=3'):
            with self.subTest(expression=expression):
                self.assertAccepted('SELECT id FROM t WHERE ' + expression + ';',
                                    'SELECT id FROM t WHERE 1=1 AND ' + expression + ';')

    def test_prefix_rejected_for_single_between_or_and_wrong_locations(self):
        for expression in ('a=1', 'a BETWEEN 1 AND 2', 'a=1 OR b=2',
                           'a=1 AND b=2 OR c=3', '(a=1 AND b=2)',
                           'id IN (SELECT x FROM u WHERE a=1 AND b=2)'):
            with self.subTest(expression=expression):
                self.assertRejected('SELECT id FROM t WHERE ' + expression + ';',
                                    'SELECT id FROM t WHERE 1=1 AND ' + expression + ';')
        self.assertRejected('SELECT a=1 AND b=2 FROM t;', 'SELECT 1=1 AND a=1 AND b=2 FROM t;')
        self.assertRejected('SELECT id FROM t WHERE a=1 AND b=2;',
                            'SELECT id FROM t WHERE a=1 AND 1=1 AND b=2;')
        self.assertRejected('SELECT id FROM t WHERE a=1 AND b=2;',
                            'SELECT id FROM t WHERE 1=1 and a=1 AND b=2;')

    def test_existing_prefix_cannot_be_removed_or_duplicated(self):
        for conjunction in ('AND', 'and'):
            source = f'SELECT id FROM t WHERE 1=1 {conjunction} a=1 AND b=2;'
            self.assertAccepted(source, source)
            self.assertRejected(source, 'SELECT id FROM t WHERE a=1 AND b=2;')
            self.assertRejected(source, source.replace('WHERE ', 'WHERE 1=1 AND '))

    def test_nested_where_eligibility_does_not_leak_to_parent_or_sibling(self):
        source = ('SELECT id FROM t WHERE id IN (SELECT x FROM u WHERE a=1 AND b=2) '
                  'OR id IN (SELECT y FROM v WHERE c=3);')
        allowed = source.replace('WHERE a=1', 'WHERE 1=1 AND a=1')
        self.assertAccepted(source, allowed)
        self.assertRejected(source, allowed.replace('WHERE id', 'WHERE 1=1 AND id'))
        self.assertRejected(source, allowed.replace('WHERE c=3', 'WHERE 1=1 AND c=3'))
        both = 'SELECT id FROM t WHERE z=0 AND id IN (SELECT x FROM u WHERE a=1 AND b=2);'
        self.assertAccepted(both, both.replace('WHERE ', 'WHERE 1=1 AND '))

class B44HavingValidatorTests(unittest.TestCase):
    def assert_valid(self, before, after):
        from formatter import validate_sql_unchanged
        validate_sql_unchanged(before, after)

    def assert_invalid(self, before, after):
        from formatter import validate_sql_unchanged
        with self.assertRaises(ValueError):
            validate_sql_unchanged(before, after)

    def test_only_eligible_having_prefix_is_accepted(self):
        for header in ('HAVING', 'having', 'HaViNg'):
            source = f'SELECT a FROM t {header} a>1 and b<3;'
            self.assert_valid(source, source.replace(header+' ', header+' 1=1 AND '))
        source = 'SELECT a FROM t WHERE a=1 AND b=2 HAVING COUNT(*)>1 AND SUM(a)>2;'
        self.assert_valid(source, source.replace('WHERE ', 'WHERE 1=1 AND ').replace('HAVING ', 'HAVING 1=1 AND '))

    def test_single_or_between_and_bracketed_are_ineligible(self):
        for predicate in ('a>1', 'a BETWEEN 1 AND 2', '(a>1 AND b<3)', 'a>1 AND b<3 OR c=4',
                          'a>(SELECT x FROM u WHERE p=1 AND q=2)'):
            source = 'SELECT a FROM t HAVING '+predicate+';'
            self.assert_invalid(source, source.replace('HAVING ', 'HAVING 1=1 AND '))

    def test_wrong_scopes_and_nested_having(self):
        source = 'SELECT a FROM t HAVING a>(SELECT MAX(x) FROM u HAVING COUNT(*)>1 AND SUM(y)>2);'
        self.assert_valid(source, source.replace('HAVING COUNT', 'HAVING 1=1 AND COUNT'))
        self.assert_invalid(source, source.replace('HAVING a>', 'HAVING 1=1 AND a>'))
        for source, location in (
            ('SELECT a FROM t JOIN u ON t.a=u.a AND u.b=2 HAVING a>1 AND a<3;', 'ON '),
            ('SELECT a FROM t HAVING a>1 AND a<3 QUALIFY a>1 AND b<3;', 'QUALIFY '),
            ('SELECT a FROM t WHERE b=1 HAVING a>1 AND a<3;', 'WHERE ')):
            self.assert_invalid(source, source.replace(location, location+'1=1 AND '))
        source = 'SELECT a FROM t HAVING a>1 AND (b<3 AND c>4);'
        self.assert_invalid(source, source.replace('(b', '(1=1 AND b'))

    def test_duplicates_removal_changes_and_case_rejected(self):
        source = "SELECT a FROM t having MAX(b)='OK' and SUM(a)>2;"
        valid = source.replace('having ', 'having 1=1 AND ')
        self.assert_valid(source, valid)
        for candidate in (valid.replace('1=1 AND ', '1=1 AND 1=1 AND '),
                          valid.replace("'OK'", "'ok'"), valid.replace('SUM(a)>2', 'SUM(a)>3'),
                          valid.replace(' and SUM(a)>2', ''), valid.replace('MAX(b)', 'MAX(a)'),
                          valid.replace('1=1', '2=2')):
            with self.subTest(candidate=candidate):
                self.assert_invalid(source, candidate)
        self.assert_invalid(valid, source)
        self.assert_valid(source, valid.replace('having', 'HAVING'))
        self.assert_valid(source, valid.replace(' and ', ' AND '))
        self.assert_invalid(valid, valid.replace('1=1 AND ', '1=1 AND 1=1 AND '))
        commented = source.replace(' and ', ' /* exact */ and ')
        self.assert_invalid(commented, commented.replace('having ', 'having 1=1 AND ').replace('/* exact */', '/* changed */'))

if __name__ == "__main__":
    unittest.main()
