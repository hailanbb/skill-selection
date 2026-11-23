#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商业活动复盘长网页照片嵌入工具 (embed_event_photos.py)
功能：将指定目录下的实拍照片（支持 .jpg, .jpeg, .png），按文件名序号自动排序，
完成 EXIF 朝向修正与高清自适应压缩后，全额转为 Base64 Data URL 内嵌进目标 HTML 文件中。
确保单个 HTML 发送到钉钉群、微信群或邮件后，任何手机均能 100% 离线高清浏览，无图片碎裂或外链失效问题。
"""

import os
import io
import re
import sys
import base64
import argparse
from PIL import Image, ImageOps

def embed_photos(photo_dir, html_path, max_dim=1200, quality=82):
    if not os.path.exists(photo_dir):
        print(f"[错误] 照片目录不存在：{photo_dir}")
        return False
    if not os.path.exists(html_path):
        print(f"[错误] 目标 HTML 文件不存在：{html_path}")
        return False

    valid_exts = ('.jpg', '.jpeg', '.png')
    files = sorted([f for f in os.listdir(photo_dir) if f.lower().endswith(valid_exts)])
    if not files:
        print(f"[警告] 目录内未找到支持的图片文件：{photo_dir}")
        return False

    print(f"[处理] 发现 {len(files)} 张照片，按文件名序号处理中...")

    html_cards = []
    for f in files:
        p = os.path.join(photo_dir, f)
        try:
            with Image.open(p) as img:
                # 纠正手机拍照 EXIF 旋转
                img = ImageOps.exif_transpose(img)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                # 高清缩放
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=quality, optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                data_url = f"data:image/jpeg;base64,{b64}"
                
            idx_str = f.split('.')[0]
            # 纯大图呈现，图片下方不带说明文字
            card_html = f'''      <!-- 照片 {idx_str} -->
      <div class="photo-card">
        <div class="photo-img-wrap">
          <img src="{data_url}" alt="现场照片 {idx_str}" loading="lazy">
        </div>
      </div>'''
            html_cards.append(card_html)
            print(f"  ✓ 已处理 {f} -> Base64 编码内嵌")
        except Exception as e:
            print(f"  ✗ 处理图片 {f} 失败：{e}")

    photos_section = '''
    <!-- 现场纪实剪影模块（纯净大图 Base64 自包含版） -->
    <div class="section-title-wrap" id="photos">
      <div class="section-title">现场纪实剪影</div>
      <span class="section-badge">全景实拍</span>
    </div>

    <div class="photos-container">
''' + '\n\n'.join(html_cards) + '''
    </div>
'''

    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 替换或追加
    pattern = r'(<!-- 现场纪实剪影模块.*?)(?=<!-- 报告尾部 -->)'
    if re.search(pattern, html_content, re.DOTALL):
        html_content = re.sub(pattern, photos_section + '\n    ', html_content, flags=re.DOTALL)
    else:
        target_before = '<!-- 报告尾部 -->'
        if target_before in html_content:
            html_content = html_content.replace(target_before, photos_section + '\n    ' + target_before)
        elif '</main>' in html_content:
            html_content = html_content.replace('</main>', photos_section + '\n  </main>')

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"[完成] 成功嵌入 {len(html_cards)} 张照片！HTML 总大小约为 {os.path.getsize(html_path) // 1024} KB")
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="将现场照片 Base64 内嵌至复盘 HTML 文件")
    parser.add_argument("--photo-dir", required=True, help="现场照片所在目录")
    parser.add_argument("--html-path", required=True, help="目标复盘 HTML 文件路径")
    parser.add_argument("--max-dim", type=int, default=1200, help="图片最大宽高（默认1200）")
    parser.add_argument("--quality", type=int, default=82, help="JPEG 压缩质量（默认82）")
    args = parser.parse_args()

    embed_photos(args.photo_dir, args.html_path, args.max_dim, args.quality)
