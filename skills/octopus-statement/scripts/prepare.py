"""Crop a reviewed Octopus screenshot and prepare non-positive transactions."""
from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from PIL import Image


def money(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('金额须为原始十进制字符串或 null')
    value = value.strip().replace('−', '-').replace('＋', '+').replace('－', '-')
    if not re.fullmatch(r'[+-]?\d+(?:\.\d{1,2})?', value):
        raise ValueError(f'非法金额：{value!r}')
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('非法金额') from exc


def prepare(source: Path, data: dict, output_dir: Path):
    with Image.open(source) as image:
        image.load()
        cutoff = data.get('cutoff_y')
        if cutoff is None:
            cutoff = image.height
        if type(cutoff) is not int or not 0 < cutoff <= image.height:
            raise ValueError('裁剪边界超出原图范围')
        records = data.get('records')
        if not isinstance(records, list):
            raise ValueError('records 必须是数组')
        selected, excluded_positive, cropped_out = [], 0, 0
        last_bottom = 0
        for record in records:
            top, bottom = record.get('top'), record.get('bottom')
            if (type(top) is not int or type(bottom) is not int
                    or not 0 <= top < bottom <= image.height or top < last_bottom):
                raise ValueError('记录坐标无效、重叠或未按原图顺序排列')
            last_bottom = bottom
            if top < cutoff < bottom:
                raise ValueError('裁剪边界跨越一笔记录，请复核分隔线')
            if top >= cutoff:
                cropped_out += 1
                continue
            amount = money(record.get('amount'))
            literal = str(record.get('amount') or '').strip().replace('＋', '+')
            if amount is not None and (amount > 0 or literal.startswith('+')):
                excluded_positive += 1
                continue
            when = record.get('datetime')
            if when is not None:
                if not isinstance(when, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', when):
                    raise ValueError('日期时间必须为 YYYY-MM-DD HH:mm 或 null')
                datetime.strptime(when, '%Y-%m-%d %H:%M')
            party = record.get('party')
            if not isinstance(party, str) or not party.strip():
                raise ValueError('交易方缺失；用“未识别”并注明原因')
            note = record.get('note', '')
            if not isinstance(note, str):
                raise ValueError('备注必须为文本')
            if (when is None or amount is None) and not note.strip():
                raise ValueError('缺失日期或金额必须写明备注')
            selected.append({
                'datetime': when, 'party': party, 'amount': str(amount) if amount is not None else None,
                'category': '待核对' if amount is None else '零金额交易' if amount == 0 else '消费',
                'note': note,
            })
        known = [Decimal(r['amount']) for r in selected if r['amount'] is not None]
        card = data.get('card_number')
        if card is not None and not isinstance(card, str):
            raise ValueError('卡号须为文本')
        balance = money(data.get('screenshot_balance'))
        payload = {
            'schema_version': 1, 'source_name': source.name,
            'cropped_name': f'{source.stem}_裁剪后.png',
            'crop_bottom': cutoff, 'card_number': card,
            'screenshot_balance': str(balance) if balance is not None else None,
            'records': selected,
            'counts': {'included': len(selected), 'excluded_positive': excluded_positive,
                       'cropped_out': cropped_out, 'unknown_amount': sum(r['amount'] is None for r in selected)},
            'known_expense_total': str(-sum(known, Decimal('0'))),
        }
        crop_path = output_dir / payload['cropped_name']
        data_path = output_dir / 'prepared.json'
        if crop_path.resolve() == source.resolve():
            raise ValueError('输出不得覆盖原图')
        if crop_path.exists() or data_path.exists():
            raise FileExistsError('输出已存在，请选择新的编号目录')
        output_dir.mkdir(parents=True, exist_ok=True)
        crop = image.crop((0, 0, image.width, cutoff))
        with crop_path.open('xb') as stream:
            crop.save(stream, format='PNG')
        with Image.open(crop_path) as saved:
            assert saved.size == crop.size and saved.tobytes() == crop.tobytes()
        with data_path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        assert json.loads(data_path.read_text(encoding='utf-8')) == payload
        return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    payload = prepare(args.source, json.loads(args.input.read_text(encoding='utf-8-sig')), args.output_dir)
    print(json.dumps({'counts': payload['counts'], 'known_expense_total': payload['known_expense_total']}, ensure_ascii=True))


if __name__ == '__main__':
    main()
