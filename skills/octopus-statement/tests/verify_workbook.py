"""Check an exported workbook against prepared input (no authoring dependencies)."""
from datetime import datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile


def verify(prepared_path: Path, workbook_path: Path):
    data = json.loads(prepared_path.read_text(encoding='utf-8'))
    records = data['records']
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(workbook_path) as archive:
        assert archive.testzip() is None
        sheet = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        assert sheet.find('.//m:pane', ns) is None, '不应冻结表头或列'
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(si.itertext()) for si in root]
        cells = {c.attrib['r']: c for c in sheet.findall('.//m:c', ns)}
        formats = ET.fromstring(archive.read('xl/styles.xml')).find('m:cellXfs', ns)

        def value(address):
            cell = cells.get(address)
            if cell is None:
                return None
            v = cell.find('m:v', ns)
            if v is None:
                return None
            if cell.attrib.get('t') == 's':
                return strings[int(v.text)]
            return v.text

        for cell in cells.values():
            if cell.find('m:v', ns) is None and cell.find('m:f', ns) is None:
                continue
            alignment = formats[int(cell.attrib.get('s', '0'))].find('m:alignment', ns)
            assert alignment is not None and alignment.attrib.get('horizontal') == 'center'
            assert alignment.attrib.get('vertical') == 'center'
        for row, record in enumerate(records, 9):
            assert int(float(value(f'A{row}'))) == row - 8
            assert value(f'C{row}') == record['party']
            assert value(f'D{row}') == record['category']
            amount = value(f'E{row}')
            if record['amount'] is None:
                assert amount is None
            else:
                assert abs(Decimal(amount) - Decimal(record['amount'])) < Decimal('0.0000001')
                assert Decimal(amount) <= 0
            if record['datetime'] is None:
                assert value(f'B{row}') is None
            else:
                dt = datetime(1899, 12, 30) + timedelta(days=float(value(f'B{row}')))
                assert dt.strftime('%Y-%m-%d %H:%M') == record['datetime']
        for address in ('A7', 'B7', 'C7'):
            assert cells[address].find('m:f', ns) is not None
        assert int(float(value('A7'))) == len(records)
        assert abs(Decimal(value('B7')) - Decimal(data['known_expense_total'])) < Decimal('0.0000001')
        assert int(float(value('C7'))) == data['counts']['unknown_amount']
        if records:
            table = ET.fromstring(archive.read('xl/tables/table1.xml'))
            assert table.find('m:autoFilter', ns) is not None
    print('Verified: records, dates, amounts, formulas, filters, centered cells and no frozen panes.')


if __name__ == '__main__':
    verify(Path(sys.argv[1]), Path(sys.argv[2]))
