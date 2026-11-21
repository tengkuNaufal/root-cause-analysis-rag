import unittest
from knowledge.retriever import lexical_ranking, query


class RetrieverTests(unittest.TestCase):
    def test_hyphenated_command_terms(self):
        docs = [{'id': 'command', 'text': 'BGP fast-external-failover detects a link flap'},
                {'id': 'other', 'text': 'OSPF hello and dead interval'}]
        result = lexical_ranking('fast external failover', docs)
        self.assertEqual([r[0] for r in result], ['command'])

    def test_no_lexical_overlap(self):
        self.assertEqual(lexical_ranking('banana', [{'id': 'a', 'text': 'BGP timers'}]), [])

    def test_invalid_query_parameters(self):
        for args in [('', None, 5), ('MTU', 'cisco', 5), ('MTU', 'frr', 0), ('MTU', 'frr', 21)]:
            with self.assertRaises(ValueError):
                query(*args)
        with self.assertRaises(ValueError):
            query('MTU', mode='unsupported')


if __name__ == '__main__':
    unittest.main()
