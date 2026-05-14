# 知识库搜索和标签筛选设计

## 1. 目标

在知识库管理后台增加搜索能力，让客服或运营可以按关键词和标签快速找到知识。

## 2. 功能范围

第一版只做两个筛选条件：

```text
query：按标题或内容搜索
tag：按标签搜索
```

接口形式：

```text
GET /knowledge?query=退款&tag=售后
```

## 3. 数据流

```text
前端输入筛选条件
-> 点击搜索
-> GET /knowledge?query=xxx&tag=xxx
-> routes.py 接收 query/tag
-> db.py 拼 SQL WHERE 条件
-> 返回匹配知识列表
-> 前端重新渲染列表
```

## 4. 不做的内容

```text
不做向量搜索
不做复杂分词
不做分页
不做高级分类体系
```

## 5. 学习重点

```text
FastAPI 查询参数怎么传
SQL LIKE 怎么做模糊搜索
前端怎么把输入框转换成 URL 参数
```
