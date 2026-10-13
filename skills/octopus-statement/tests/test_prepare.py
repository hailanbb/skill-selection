from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

spec = importlib.util.spec_from_file_location('prepare', Path(__file__).parents[1] / 'scripts' / 'prepare.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / '中文 空格目录'
        self.root.mkdir()
        self.source = self.root / '八达通.jpg'
        im = Image.new('RGB', (100, 600))
        im.putdata([(x % 256, y % 256, (x + y) % 256) for y in range(600) for x in range(100)])
        im.save(self.source)
        self.data = {'cutoff_y': 500, 'records': [
            {'top': 100, 'bottom': 200, 'datetime': '2026-10-13 14:54', 'party': '港鐵', 'amount': '-5.90'},
            {'top': 200, 'bottom': 300, 'datetime': '2026-10-13 13:59', 'party': '八達通卡有限公司', 'amount': '+300.0'},
            {'top': 300, 'bottom': 400, 'datetime': '2026-10-13 13:00', 'party': '九巴／龍運', 'amount': '0.0'},
            {'top': 400, 'bottom': 500, 'datetime': None, 'party': '港鐵', 'amount': None, 'note': '日期和金额截断'},
            {'top': 500, 'bottom': 600, 'datetime': '2026-10-12 12:00', 'party': '交通費用補貼', 'amount': '+12.5'},
        ]}

    def run_prepare(self, data=None):
        return module.prepare(self.source, data or self.data, self.root / '输出')

    def test_crop_filter_unicode_and_unknown(self):
        result = self.run_prepare()
        self.assertEqual(result['counts'], {'included': 3, 'excluded_positive': 1, 'cropped_out': 1, 'unknown_amount': 1})
        self.assertEqual(result['known_expense_total'], '5.90')
        self.assertEqual(result['records'][1]['category'], '零金额交易')
        self.assertEqual(result['records'][2]['category'], '待核对')
        self.assertEqual(result['records'][0]['datetime'], '2026-10-13 14:54')
        self.assertEqual(json.loads((self.root / '输出' / 'prepared.json').read_text(encoding='utf-8')), result)
        with Image.open(self.source) as original, Image.open(self.root / '输出' / '八达通_裁剪后.png') as cropped:
            self.assertEqual(cropped.size, (100, 500))
            self.assertEqual(cropped.tobytes(), original.crop((0, 0, 100, 500)).tobytes())

    def test_no_subsidy_full_image(self):
        data = deepcopy(self.data)
        data['cutoff_y'] = None
        data['records'] = data['records'][:1]
        self.assertEqual(self.run_prepare(data)['crop_bottom'], 600)

    def test_positive_without_plus_excluded(self):
        data = deepcopy(self.data)
        data['records'][0]['amount'] = '5.9'
        self.assertEqual(self.run_prepare(data)['counts']['excluded_positive'], 2)

    def test_plus_zero_excluded(self):
        data = deepcopy(self.data)
        data['records'][2]['amount'] = '+0.0'
        self.assertEqual(self.run_prepare(data)['counts']['included'], 2)

    def test_no_overwrite(self):
        self.run_prepare()
        with self.assertRaises(FileExistsError):
            self.run_prepare()

    def test_cutoff_crossing_rejected(self):
        data = deepcopy(self.data)
        data['cutoff_y'] = 450
        with self.assertRaises(ValueError):
            self.run_prepare(data)

    def test_invalid_date_rejected(self):
        data = deepcopy(self.data)
        data['records'][0]['datetime'] = '2026-02-30 12:00'
        with self.assertRaises(ValueError):
            self.run_prepare(data)

    def test_missing_amount_needs_note(self):
        data = deepcopy(self.data)
        data['records'][0]['amount'] = None
        with self.assertRaises(ValueError):
            self.run_prepare(data)

    def test_overlap_rejected(self):
        data = deepcopy(self.data)
        data['records'][1]['top'] = 150
        with self.assertRaises(ValueError):
            self.run_prepare(data)

    def test_non_decimal_amount_rejected(self):
        for value in ['NaN', '1e2', '', True, 12.5, '1.999']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.money(value)


if __name__ == '__main__':
    unittest.main()
