---
workflow_schema: 3
document_type: context_index
project_id: PRJ-MINATO-ASSET
record_status: active
updated_at: 2026-10-08
updated_by: Claude（はやて承認、W-0001-C01）
---

# Context一覧

案件知識のRouter。20セクションの `プロジェクトコンテキスト.md` と、存在するセクション別詳細のCTX本体から生成し、手動で二重管理しない。分離済み項目の配置先は詳細ファイルとし、メイン要約を別のCTXとして登録しない。機密項目の概要は転記せず漏出を防ぐ。

| Context ID | 種別 | 概要 | 適用範囲 | knowledge | approval | lifecycle | blocking | 秘 | 配置先 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CTX-0001 | objective | 所在把握と棚卸負荷の軽減 | project | confirmed | pending | active | false | - | プロジェクトコンテキスト.md |
| CTX-0002 | scope | 3拠点の要件定義 | RQ-0001 | assumption | pending | active | false | - | プロジェクトコンテキスト.md |
| CTX-0003 | out_of_scope | 消耗品在庫管理は対象外 | project | confirmed | approved | active |  | - | プロジェクトコンテキスト.md |
| CTX-0004 | stakeholder | 顧客窓口は総務部 松本主任 | project | confirmed | approved | active |  | - | プロジェクトコンテキスト.md |
| CTX-0005 | authority | 最終判断者が未確定 | project | unknown | pending | active | false | - | プロジェクトコンテキスト.md |
| CTX-0006 | requirement | スマホQRで貸出・返却・棚卸 | project | confirmed | pending | active | false | - | プロジェクトコンテキスト.md |
| CTX-0007 | constraint | 2027年3月末の棚卸で使いたい | project | confirmed | pending | active | false | - | プロジェクトコンテキスト.md |
| CTX-0008 | conflict | 第一段階の目的の優先度が食い違う | project | conflict | pending | active | false | - | プロジェクトコンテキスト.md |
| CTX-0009 | unknown | 対象物品の範囲が未確定 | project | unknown | pending | active | false | - | プロジェクトコンテキスト.md |
| CTX-0010 | unknown | 連携・利用環境の条件が未確認 | project | unknown | pending | active | false | - | プロジェクトコンテキスト.md |
| CTX-0011 | acceptance | 要件定義書の合意方法は未定 | RQ-0001 | unknown | pending | active | false | - | プロジェクトコンテキスト.md |
| CTX-0012 | commercial_boundary | 契約と予算が未確定 | project | unknown | pending | active | false | - | プロジェクトコンテキスト.md |
| CTX-0013 | unknown | データクレンジング担当が未確定 | project | unknown | pending | active | false | - | プロジェクトコンテキスト.md |

行例：`| CTX-0001 | objective | 月次締め短縮 | project | confirmed | approved | active | false | - | プロジェクトコンテキスト.md |`
