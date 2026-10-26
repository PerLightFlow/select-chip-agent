import unittest
from core.domain import validate_requirements, evaluate, rank_candidates, reciprocal_rank_fusion, split_blocks


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.req = {'key':'ram_mb','op':'gte','value':128,'unit':'MiB','hard':True,'conditions':''}
        self.fact = {'value':256,'unit':'MiB','conditions':'','confirmed':True,'evidence_valid':True,'evidence_id':1}

    def test_missing_and_unconfirmed_are_unknown(self):
        for fact in [None, {}, {**self.fact,'confirmed':False}, {**self.fact,'evidence_valid':False}]:
            self.assertEqual(evaluate(self.req,fact)['status'],'unknown')

    def test_units_conditions_and_boolean_not_numeric(self):
        for patch in [{'unit':'GB'},{'conditions':'外部内存配置'},{'value':True},{'value':float('nan')}]:
            self.assertEqual(evaluate(self.req,{**self.fact,**patch})['status'],'unknown')

    def test_hard_failure_cannot_be_outvoted(self):
        a={'model':'a','facts':{'ram_mb':{**self.fact,'value':16}},'lifecycle':'production'}
        b={'model':'b','facts':{'ram_mb':self.fact},'lifecycle':'nrnd'}
        result=rank_candidates([a,b],[self.req])
        self.assertEqual(result[0]['model'],'b')
        self.assertEqual(result[1]['status'],'fail')

    def test_no_constraints_is_not_pass(self):
        self.assertEqual(rank_candidates([{'model':'a','facts':{}}],[])[0]['status'],'unknown')

    def test_requirement_validation(self):
        for items in [None,{},[{'key':'bad key','value':1}],[{**self.req,'value':True}],[{**self.req,'hard':'false'}]]:
            with self.assertRaises(ValueError):validate_requirements(items)

    def test_table_stays_with_units(self):
        table='| mode | power |\n| typ | 2 mW |\nNote: 1 MHz only.'
        chunks=split_blocks('intro\n\n'+table+'\n\nend',20)
        self.assertIn(table,chunks)

    def test_rrf_dedup_and_multiple_evidence(self):
        ids,scores=reciprocal_rank_fusion([1,1,2],[2,3])
        self.assertEqual(ids[0],2)
        self.assertAlmostEqual(scores[1],1/61)

if __name__=='__main__':unittest.main()
