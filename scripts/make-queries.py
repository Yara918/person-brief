#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""person-brief · 生成检索查询清单（分层查询）

用法：
    python make-queries.py --person "人名" --company "公司名" --role "职位"
输出：检索清单（含降级链提示 + 分层社媒查询词）
"""
import argparse
import json
from pathlib import Path


def build_queries(person, company, role):
    return {
        "P1 身份与履历": [
            f'"{person}" "{company}" {role}', f'"{person}" 履历 任职',
        ],
        "P2 公开言论": [
            f'"{person}" 采访 OR 演讲 OR 发言', f'"{person}" 报道 评价',
        ],
        # 社媒：必查 4 平台
        "P3 社媒（必查）": [
            f'"{person}" 微博', f'site:linkedin.com "{person}"',
            f'site:x.com "{person}"', f'site:douyin.com "{person}"',
        ],
        # 按行业查（长尾）
        "P4 社媒（按行业）": [
            f'"{person}" 小红书 OR B站 OR 知乎 OR 脉脉',
        ],
        # 降级链提示
        "P5 降级定位（查无此人时）": [
            f'"{company}" 法定代表人', f'"{company}" 董事长 OR CEO',
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="person-brief 检索清单")
    ap.add_argument("--person", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--role", default="")
    ap.add_argument("--out", default="work/queries.json")
    args = ap.parse_args()

    result = {
        "person": args.person,
        "company": args.company,
        "role": args.role,
        "blocks": build_queries(args.person, args.company, args.role),
        "note": "锁定规则：人名+公司+职位查到则研究该人；查不到 → 降级查法定代表人 → 董事长 → CEO → 高管 → 部门负责人。"
                "社媒每平台独立查询，命中写账号名+链接，查无写未检索到+检索记录。",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
