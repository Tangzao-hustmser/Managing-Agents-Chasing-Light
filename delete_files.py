#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import pathlib

# 设置工作目录
work_dir = r'd:\大学\大三\智能体大赛\Managing-Agents-Chasing-Light'
os.chdir(work_dir)

# 要删除的文件列表
files_to_delete = [
    'BUGFIX.md',
    'FIXES.md',
    'FRONTEND_GUIDE.md',
    'INTERFACE_GUIDE.md',
    'INTERFACE_STATUS.md',
    'QUICKSTART.md',
    'README.md',
    'check_models.py',
    'test_imports.py',
    'test_features.py'
]

print("=" * 60)
print("开始删除文件...")
print("=" * 60)

deleted_count = 0

# 删除文件
for file in files_to_delete:
    file_path = os.path.join(work_dir, file)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            deleted_count += 1
            print(f'✓ 已删除: {file}')
        else:
            print(f'✗ 不存在: {file}')
    except Exception as e:
        print(f'✗ 删除失败 {file}: {e}')

print("\n" + "=" * 60)
print(f"总共删除: {deleted_count} 个文件")
print("=" * 60)

# 列出剩余文件
print("\n删除后的文件清单:")
print("-" * 60)

remaining_files = []
remaining_dirs = []

for item in sorted(os.listdir(work_dir)):
    item_path = os.path.join(work_dir, item)
    if os.path.isfile(item_path):
        remaining_files.append(item)
    elif os.path.isdir(item_path) and item != '.git' and item != '__pycache__':
        remaining_dirs.append(item)

# 显示文件
if remaining_files:
    print("\n【文件】")
    for f in remaining_files:
        print(f'  • {f}')

# 显示目录
if remaining_dirs:
    print("\n【目录】")
    for d in remaining_dirs:
        print(f'  📁 {d}/')

print("-" * 60)
print(f"共有 {len(remaining_files)} 个文件，{len(remaining_dirs)} 个目录")
