#!/usr/bin/env python
"""
订单/物流数据层验证脚本。

阅读顺序：
1. 初始化数据库表
2. 新增订单
3. 查询订单
4. 更新订单状态
5. 新增物流
6. 查询物流
7. 更新物流状态

这个脚本不经过前端和 FastAPI，只直接测试 db.py 里的数据库函数。
"""
from app.storage.db import (
    init_db,
    get_order_status,
    get_logistics_status,
    insert_order,
    insert_logistics,
    update_order_status,
    update_logistics_status,
)


def main() -> None:
    # 第一步：先初始化数据库和表。
    # 如果表已存在，CREATE TABLE IF NOT EXISTS 会自动跳过，不会重复创建。
    init_db()

    print("=" * 60)
    print("订单/物流 数据层最小验证脚本")
    print("目标：验证 新增 -> 查询 -> 更新 -> 再查询 这条链路是否可用")
    print("=" * 60)

    # 第二步：准备测试编号。
    # 为了方便重复运行脚本，这里使用固定编号；如果遇到 UNIQUE 冲突，可以换成新编号。
    order_no = "A101"
    tracking_no = "L101"
    user_id = "u001"

    print("\n[步骤1] 新增订单")
    print(f"插入订单: order_no={order_no}, user_id={user_id}, status=默认(pending)")
    insert_order(order_no, user_id)
    order_status = get_order_status(order_no)
    print(f"查询订单状态 -> {order_status} (预期: pending)")

    print("\n[步骤2] 更新订单状态")
    ok = update_order_status(order_no, "shipped")
    print(f"更新是否成功 -> {ok} (预期: True)")
    order_status = get_order_status(order_no)
    print(f"再次查询订单状态 -> {order_status} (预期: shipped)")

    print("\n[步骤3] 新增物流")
    print(f"插入物流: tracking_no={tracking_no}, order_no={order_no}, status=默认(pending)")
    insert_logistics(tracking_no, order_no)
    logistics_status = get_logistics_status(tracking_no)
    print(f"查询物流状态 -> {logistics_status} (预期: pending)")

    print("\n[步骤4] 更新物流状态")
    ok = update_logistics_status(tracking_no, "in_transit")
    print(f"更新是否成功 -> {ok} (预期: True)")
    logistics_status = get_logistics_status(tracking_no)
    print(f"再次查询物流状态 -> {logistics_status} (预期: in_transit)")

    print("\n完成：如果所有“预期”都一致，说明你的数据层核心流程已经打通。")


if __name__ == "__main__":
    main()
