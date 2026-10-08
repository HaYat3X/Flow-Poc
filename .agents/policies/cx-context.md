# CX Context運用Policy

`03_CX_コンテキスト/` は現在管理対象となっている案件知識の正本と、引き継ぎのための要約・参照を置く。イベントログではない。進捗・次アクション・期間の正本はCT・Workとし、Contextの要約を独立した実行管理に使わない。
実際にWorkへ適用可能なのは `lifecycle_state: active` のものに限る。`scheduled` や `suspended` も管理対象として保持する。

## 1. Context ID体系

- 正本IDは `CTX-xxxx`（4桁通番、再利用禁止）とする。種別（目的・要求・制約・方針・受入条件など）はID接頭辞で区別せず、項目内の `種別` 属性で表す。
- Work内の反映候補IDは `C-CTX-xxx`（Work内一意）とする。途中Syncで正本化するときに未使用のCTXを発行する。終了同期ではCloseの承認用反映案で未使用IDを予約し、Syncは同じIDを適用する。
- `REQ-xxxx` の新規発行はしない。要求も `CTX-xxxx` で管理する。既存資料に `REQ-xxxx` がある場合は `トレーサビリティ.md` で `CTX-xxxx` との対応を維持する。
- 依頼 `RQ-`、入力資料 `MAT-`、Work `W-`、Knowledge `K-<分類>-` は従来通りとし、発行済みIDを再利用しない。意思決定・リスク・課題の新規正本もCTX-IDを使う。既存DEC/RSK/ISSは `legacy_id` として保持し、再発行しない。

## 2. 共通属性と列挙値

確度・承認・適用性・ライフサイクルを分離する。

| 属性 | 列挙値 | 意味 |
| --- | --- | --- |
| `applicability` | `applicable` / `not_applicable` | 適用性。確度とは別軸 |
| `knowledge_state` | `confirmed` / `assumption` / `unknown` / `conflict` | 知識の確度 |
| `approval_state` | `not_required` / `pending` / `approved` / `rejected` | 組織としての利用承認 |
| `lifecycle_state` | `active` / `scheduled` / `suspended` / `retired` | 採用・運用上の段階 |
| `blocking` | `true` / `false` | 未解決時のWork可否 |
| `confidentiality` | 分類ラベルのみ | アクセス制御ではない |

関連属性：

- `approval_ref`：承認根拠への汎用参照。`MAT-`／議事録／顧客メール／`DEC-` を許容する。決定項目を参照する場合は `decision_ref: CTX-xxxx` を使う。旧DEC参照はlegacy_id経由で追跡する。
- `approved_by`：人・役割。`DEC-ID` ではない。`approved_at` と組で使う。
- `basis`：根拠。`evidence`（資料参照）／`rationale`（専門判断の理由文）／`approval_ref`（案件上承認）のいずれか。
- `required_by`：意味上の制約のみ（例：「基本設計開始前」「MS-003まで」）。具体日付は持たない。
- `resolution_task_ref`：対応Work/TODOへの参照（例：`W-0007#T-001`）。解決する作業の期限・担当・進捗はWorkの実体に置く。
- `working_assumption`／`working_assumption_ref`：`conflict` 時の作業上採用値とその承認根拠。
- `applies_to`：適用範囲（`project` または `CTX-`／`RQ-`／機能・リリース名）。
- `replaced_by`：置換時のみ使用。常用しない。

必須規則：

- 常時必須：`id`、`applicability`、`applies_to`
- `applicability: applicable` の場合のみ必須：`knowledge_state`、`approval_state`、`lifecycle_state`
- 条件付き必須：
  - `confirmed`／`conflict` では `evidence` または `basis` 必須。`assumption` では `basis`／`evidence`／`rationale`／`approval_ref` のいずれか必須。`unknown` では `evidence` を要求しない。
  - `unknown`／`conflict` では `resolution_task_ref`、`required_by`、`impact` を条件付き必須。
  - `not_applicable` では `reason` 必須とし、他3状態は評価対象外とする。
  - `unknown`／`conflict`／`approval pending` では `blocking` を条件付き必須とする。未指定時は安全側で `blocking: true` として扱う。
  - `approved` では `approval_ref`、`approved_by`、`approved_at` を条件付き必須とする（`not_required`／`pending` 時は不要）。

## 3. CXに残せる状態の組み合わせ

| applicability | knowledge_state | approval_state | lifecycle_state | CX可否 |
| --- | --- | --- | --- | --- |
| `applicable` | `confirmed`／`assumption`／`unknown`／`conflict` | `not_required`／`pending`／`approved` | `active`／`scheduled`／`suspended` | 可（`pending`／`unknown`／`conflict` はblocking規則に従う） |
| `applicable` | — | `rejected` | — | 不可（`WK` へ戻すか廃棄） |
| `applicable` | — | — | `retired` | 不可（CXから除外しCT更新履歴に記録の上でAXへ。猶予は `suspended`） |
| `not_applicable` | — | — | — | `reason` 付きで残すか項目自体を置かないかは適用プロファイルで決める |

禁止例：`active` × `rejected`、`retired` のCX残留。

## 4. 期限・対応の正本ルール

- リスク・課題自体の対応期限・担当・対応方針は該当CTX項目の `due_at`、`owner`、`response` に記録する。
- 実行作業は `resolution_task_ref: W-xxxx#T-xxx` で紐づける。作業の期限・進捗はWorkを参照し、Context側で複製しない。
- 不明な期限は `unknown` と明記する。具体日付がある場合はISO日付を使う。現在地の判断待ち・阻害要因はこれらを参照して生成する。

## 5. Candidate → Close → Sync → CX反映の状態遷移

```text
作業メモのTODO記録 → 反映候補.md C-CTX-xxx（候補）
  → Closeで 反映 / 見送り / 保留 / 残作業化 を判断
  → Syncで承認済みのみ CTX-xxxx 新規 / 更新 / 廃止として反映
  → Context一覧・トレーサビリティ・更新履歴を同時更新
```

- Closeは採否と終了状態を判断し、正本への書込は行わない。
- Syncは承認済み判断の同期のみ行い、採否判断は行わない。
- Work途中の承認は終了を待たずSyncできる。Work終了時はCloseで承認済み終了判断を保存し、終了同期でSyncが状態確定まで行う。詳細は `.agents/policies/work-close-contract.md` に従う。
- 新規は未使用 `CTX-xxxx` 発行、更新は同一ID更新、置換は `replaced_by` 記録、失効は `retired` 化後にCX除外＋AX移送とする。
- 反映時は一覧・実体・frontmatter・関連ID・参照パス・更新履歴を同じ変更単位で更新する。

### Context候補の型と反映先

Workの `C-CTX-xxx` 候補は、自由記述の反映先パスではなく、次の候補種別を必ず持つ。Syncは候補種別と任意の反映先セクション番号から、メイン内または分離済み詳細の固定セクションへ反映する。新しい項目種別・ファイル名を独断で作らない。

| 既定セクション | 許可する候補種別 |
| --- | --- |
| 02. 案件の背景 | `objective` |
| 03. ゴール・成功条件 | `success_condition` / `scope` / `out_of_scope` / `constraint` / `commercial_boundary` / `quality_policy` / `acceptance` |
| 04. 対象業務 | `business_rule` |
| 05. システム概要 | `requirement` / `expectation` / `solution_policy` / `architecture` / `non_functional` |
| 06. 外部システム・連携 | `external_dependency` |
| 07. データ概要 | `data` |
| 09. 開発・運用ルール | `operation` |
| 10. プロジェクト体制 | `stakeholder` / `authority` |
| 13. 課題・リスク | `risk` / `issue` |
| 14. 未決事項 | `assumption` / `unknown` / `conflict` |
| 15. 重要な経緯・意思決定 | `decision` |

追加先は次に限る。候補の補足属性 `反映先セクション` に2桁番号を指定し、反映後のCTX属性に `context_section` を残す。空欄・`-` または旧10列候補は既定先として扱う。

| 明示指定できるセクション | 許可する候補種別 |
| --- | --- |
| 08. 環境 | `operation` |
| 11. コミュニケーション | `operation` |
| 16. 注意事項・ハマりポイント | `constraint` / `business_rule` / `external_dependency` / `operation` |

既存CTXの更新・廃止は現在の配置を維持する。意味や種別の変化でセクションも移す場合は、同一IDを保ち、移動先と理由を承認対象に含める。分離済みなら詳細側だけを更新し、メイン要約をその正本から同期する。

候補は `### <変更内容がわかるタイトル> (C-CTX-xxx)` ごとに、現在値・変更案・理由・影響・根拠を自然言語で記録する。現在値と変更案は `#### 現在値` / `#### 変更案` の下に複数段落で書ける。番号や横長の表だけで説明しない。元TODO・候補種別・変更種別・対象CTX・適用範囲・状態・根拠・反映先セクションは補足属性の `- 項目名: 値` で保持する。意思決定・リスク・Knowledge・Productの候補も同じ文章形式とし、各テンプレートの項目を保持する。旧候補表は互換読取のみとし、過去の固定入力・承認封印を書き換えない。

候補には少なくとも候補ID、候補種別、変更種別、対象CTX（新規は `新規`）、適用範囲、現在値、変更案、情報状態、根拠を記録する。候補種別を判断できない場合は新種別を作らず、未解決事項としてCloseへ渡す。意思決定・リスク・課題候補の既存C-DEC/C-RSK/C-ISSは、それぞれdecision/risk/issue型のCTXへ反映する。

意思決定には `decided_by`、`decided_at`、`rationale`、`impact` を残す。リスク・課題には `cause`、`impact`、`response`、`owner`、`due_at`、`resolution_task_ref` を残す。リスクには `likelihood` も記録する。未確定属性はunknownとし、未対応の課題・リスクを解決済みとしない。

## 6. unknown／conflictのWork側扱い

- `blocking: true` がある場合、関連Workの開始・計画承認を止める。
- `blocking: false` の場合、`assumption` または `unknown` を前提として作業継続可とするが、前提IDをWork入力に記録する。
- `conflict` は指定がなければ常に `blocking` として扱う。継続時のみ例外とし、`working_assumption` と `working_assumption_ref` を記録する。
- `required_by` を過ぎた `unknown`／`conflict` は現在地の判断待ちへ上げる。
- Work開始後に `blocking` 項目が発生した場合は中断・継続判断を行う。継続にはPM承認と前提IDの記録を必須とし、判断と根拠を作業メモ＋CT更新履歴に残す。

## 7. 更新・置換・失効規則

- 更新：現在値が変わったら同一 `CTX-xxxx` を更新し、CT更新履歴へ理由・根拠を記録する。
- 置換：意味的に別項目へ置き換わった場合のみ `replaced_by` を使い、旧項目は `retired` 化してCX除外＋AX移送する。常用しない。
- 失効：不要になったら `retired` 化し、CXから除外してCT更新履歴に記録の上でAXへ移す。移行猶予の表現には `suspended` を使う。
- `rejected` はCXに置かず `WK` へ戻すか廃棄する。
- 各依頼の受付時の原本（`01_IN_入力/入力/`）とWork入力（`04_WK_作業/W-xxxx_Work名/入力/`）は編集・上書き・削除しない。

## 8. 機密情報の扱い

- `confidentiality` は分類ラベルであり、アクセス制御そのものではない。
- 同じ権限で読める場所へのファイル分離やSkill指示文による読取制限はセキュリティ境界にしない。実制御は別ワークスペース・権限・暗号化・ACLで行う。
- `Context一覧.md` の概要欄から機密が漏れないよう、生成時に機密項目の要約・転記ルールを適用する。

## 9. フェーズ別適用プロファイル

最小核7項目は必ず存在させる。値の確定は要求せず、`unknown` または `not_applicable`（`reason` 必須）を許可する。

最小核：

1. 目的・成功条件
2. 対象／対象外
3. ステークホルダーと判断権限
4. 要求・期待の一覧
5. 前提・制約・未確認事項
6. 受入条件の概要
7. 根拠参照と適用範囲

段階追加：

- Pre-Sales：解決方針、見積前提、契約上の境界、主要リスク
- 要件定義：機能・非機能、業務ルール、データ、外部IF
- 設計以降：アーキテクチャ、`トレーサビリティ.md`、テスト、移行、運用

`トレーサビリティ.md` は最初から完成形を要求せず、IDが発生した時点から徐々に接続する。

## 10. Contextの物理配置と自動分割

初期は `03_CX_コンテキスト/プロジェクトコンテキスト.md` を入口とする。メインは常に残し、20セクションを番号順の `## N. セクション名` 見出しで保持する。CTXの意味・IDと物理配置を分離し、Workや台帳は `CTX-xxxx` を参照する。

課題・リスク・QAの対応管理はFlow外で行う。管理票の担当・期限・対応状態をCTXとして管理しない。メインの13・14には案件全体に関わる影響・前提・未決事項の要約を残す。既存のCTXや未確認の前提は保持し、提供された回答・対応結果から確定した要求・仕様・意思決定が生じた場合は該当するCTXを承認後に追加・更新する。

承認済み反映後に次の固定規則で詳細を分離する。採否は変更せず、事前承認された構造保守とする。終了同期ではCloseの承認用targetに分離と要約を含める。

1. メインの1セクションの本文が6,000文字を超えたら、そのセクションの詳細を分離する。
2. メイン全体の本文が25,000文字を超えたら、未分離の詳細セクションを本文文字数の多い順に分離し、25,000文字以下にする。同じ文字数なら小さいセクション番号を優先する。
3. 01・12・17・20は識別情報・要約としてメインに残す。これらの超過や分離後の要約による超過は、正本を削除せず正本参照と短い要約に整理する。

文字数はUnicodeの文字数で数え、バイト数・行数・CTX件数は使わない。frontmatter・見出し行・空行・各行の前後空白・改行を除き、表・箇条書き・リンク・コードを含むMarkdown本文を数える。コードブロック内の見出し風の文字列は本文として数える。閾値ちょうどは分離不要とする。

分離先は同じCXフォルダの `NN_セクション名.md` に固定する。

| 番号 | セクション名 |
| --- | --- |
| 02 | 案件の背景 |
| 03 | ゴール・成功条件 |
| 04 | 対象業務 |
| 05 | システム概要 |
| 06 | 外部システム・連携 |
| 07 | データ概要 |
| 08 | 環境 |
| 09 | 開発・運用ルール |
| 10 | プロジェクト体制 |
| 11 | コミュニケーション |
| 13 | 課題・リスク |
| 14 | 未決事項 |
| 15 | 重要な経緯・意思決定 |
| 16 | 注意事項・ハマりポイント |
| 18 | 関連資料 |
| 19 | 引き継ぎ時に最初に読むもの |

例：05の詳細は `05_システム概要.md`。詳細にはメインと同じ `## 5. システム概要` 見出しと配下の小見出し・表・CTX項目を置く。不要な空の詳細ファイルは作らない。詳細ファイルの文字数による再分離は行わず、必要なら別途構造を提案して承認を得る。

分割時は次を同じ変更単位で行う。

- 表・CTX項目の途中で切らず、セクションの詳細を移動する。メインには短い要約、同期時点、同一フォルダ内へのMarkdown詳細リンクを残す。
- 詳細の正本は移動先のみとし、メインに同じCTX見出しを残さない。要約は詳細から同期し、独立した候補・正本にしない。
- `CTX-xxxx` を変更しない。メインの案件識別情報（project_id、flow_project_id、project_name、initialized_from_request）を移動しない。
- 分離済みならメインと存在する詳細の `context_layout` を `split` にする。各詳細の `context_section` は2桁番号、`project_id` はメインと同じ値にする。
- `Context一覧.md`、トレーサビリティ、更新履歴、パス参照を同時に更新する。
- 分割後は閾値を下回っても自動再結合しない。再結合は別途の明示承認を必要とする。

Work開始ではメインとContext一覧を入口に、対象作業に関連する詳細・CTXだけを読む。全詳細ファイルの一括読込みを既定にしない。

## 11. Context一覧とトレーサビリティの生成・検査

- `03_CX_コンテキスト/Context一覧.md` は案件知識のRouter、`02_CT_管理/現在地.md` は案件進行のRouterとする。
- `Context一覧.md` の状態列は単一列にまとめず、最低限 `knowledge`、`lifecycle`、`blocking`、`秘` を持つ。`approval` と `applicability` は用途に応じて列またはフィルタに含める。
- 一覧はAIが手動で二重管理せず、本体から生成・検査できる形にする。生成と関連ファイルの更新を同じ変更単位で終えてから、AGENTS.mdの共通検査でまとめて検査する。一覧の生成直後に別途実行しない。
- `トレーサビリティ.md` は `CTX-`／`RQ-`／`W-`／`DEC-`／`MAT-` 間の関係（`根拠`・`決定元`・`反映`・`置換`など）を記録する。
- 検査内容：`CTX-xxxx` の重複、一覧と実体の対応（ID・`knowledge_state`・`lifecycle_state`・参照パス）、機密項目の概要漏出がないこと。

## 12. フォルダ・ファイル構成

```text
03_CX_コンテキスト/
  プロジェクトコンテキスト.md
  Context一覧.md
  トレーサビリティ.md
```

- `プロジェクトコンテキスト.md` と分割後のContext MDのfrontmatterは `workflow_schema: 3`、`document_type: project_context`、`context_layout: single | split` とする。
- 本文はテンプレートの20セクションに沿った自然言語の文章・箇条書きを基本とする。内容・理由・影響を先に説明し、IDや属性表だけの台帳へ置き換えない。比較に適した利用者・機能・環境等はテンプレートの表を使ってよい。個別追跡する要求・判断等だけ、該当小見出しの下に `#### <タイトル> (CTX-xxxx)` と本文、補足属性の箇条書きを記録する。既存の `###` / `#### CTX-xxxx: <タイトル>` と属性表も読み取れる。表の全セルや空欄、要約にはIDを発行しない。空の `CTX-TBD` 項目は作らず、承認済み候補の初期化・反映時に追加する。
- 失効項目はファイルを残したまま `retired` で残さず、CXから除外してAXへ移す。

### Flow外の課題管理との境界

- 課題・リスク・QAの管理票はFlowの作成・登録・更新・同期・検査対象にしない。外部の担当・期限・対応状態をContextへ二重管理しない。
- Workには作業上の未解決事項・影響・次の対応・引継ぎ先を残す。外部管理票への登録や確認を毎TODOの条件にしない。
- 提供された回答・対応結果から確定した要求・仕様・意思決定をContextへ反映する場合は、通常の承認・候補・同期の手順を使い、資料・Workを根拠として参照する。
- 外部資料が提示された場合は参照できるが、外部管理票の存在・ID・状態をContext反映の必須条件にしない。既存のCTX・根拠・過去のWork入力・承認封印は変更しない。

記録例（属性の必須条件は2節を参照）：

```markdown
#### 貸出時に利用者を確認する (CTX-xxxx)

備品を貸し出す際は利用者を確認し、返却先を追跡できるようにする。確認する情報の詳細は顧客との要件確認で確定する。

補足属性：

- 種別: requirement
- applies_to: project
- applicability: applicable
- knowledge_state: assumption
- approval_state: pending
- lifecycle_state: active
- blocking: true
- confidentiality: -
- basis: MAT-xxxx#p3
```

### セクションごとの正本と要約

| 扱い | 対象 | 更新規則 |
| --- | --- | --- |
| 案件知識の正本 | 02〜11、13〜16 | 承認済みの現在値を更新。分離済みなら詳細を更新してメイン要約を同期 |
| 基本情報・参照 | 01 | 識別情報をfrontmatterと揃え、担当者は10を参照。期間・フェーズはCTから同期 |
| 実行状態の要約 | 12、17 | CT・Plan・Workを参照し、対象ID・参照元・同期時点を明記。個々のTODOを複製しない |
| 案内・要約 | 18〜20 | 関連資料の所在・版、読む順番、案件全体のサマリを正本から整理 |

20には新しい要求・判断・計画を作らない。15には現在有効な仕様の理由を説明する重要な判断だけを置き、全作業履歴はCT・Work、失効判断はAXへ置く。16の汎用ノウハウはKnowledgeへリンクする。契約原本はIN、作業の予定日・進捗はCT・Workを参照する。ただし意思決定日やリスク・課題自身の対応期限はCTX属性として保持する。

## 13. Contextを継続して育てる

- 初回受付で案件識別情報と最小核を同じ正本に初期化する。目的、ステークホルダー、スコープ、要求、前提・未確認、受入条件を少なくとも各1項目持ち、根拠と適用範囲を付ける。未確認値はunknown、適用外はreason付きnot_applicableとする。未確認だけを理由に一律にWorkを止めず、影響に基づきblockingを判断する。
- 依頼本文はCTの依頼、依頼別計画はCTの進行計画を正本として保存する。依頼の追加受付・改訂では案件共通情報とRQ固有情報の差分を照合し、目的・要求・対象範囲・受入条件・前提等の承認された現在値を更新する。RQ固有のContextはapplies_toにRQ-IDを記録し、RQ本文をContext本文に丸ごと複製しない。
- Planの作成・拡張・再計画では、計画で明らかになった目的・前提・方針・制約・リスク・未確認事項の具体差分を承認案に含める。承認対象に含まれる差分だけを計画保存と同時にContextへ反映する。Work候補・順序・進捗や計画本文はCXへ複製しない。
- 依頼・Planの作成・改訂ごとにContext反映要否を確認する。差分がなければ更新不要理由をCT更新履歴へ記録し、Contextの本文更新は強制しない。差分には対象CTX・現在値・変更案・確度・適用範囲・根拠を示し、RQ-IDとPlanの改訂を根拠・トレーサビリティで追跡する。案の段階で承認済みの現在値を上書きしない。
- Work中は観測対象だけでなく新たに得た現在値を候補化する。Closeで案件全体の現在値と照合し、更新不要なら理由を記録する。
- Syncは承認された差分を新規・更新・廃止として反映する。同じ意味の項目を新規IDで重複登録せず、既存CTXを更新する。
- Context項目数を増やすこと自体を目的にしない。失効情報は除外し、根拠・未確認事項・次の解決作業が追跡できる現在値を維持する。
- 更新タイミングは初回受付、依頼の追加・改訂承認、Plan承認、途中の承認済みSync、Work終了同期のままとする。各タイミングで1・12・17・20と分離済みセクションの要約の更新要否も確認する。候補ゼロでもCT・Workの状態変更で要約が変わるなら同期する。
- 要約の根拠・参照元・同期時点を残し、未承認の予定や判断を確定情報にしない。差分がなければ全セクションの書き直しや更新日時だけの変更は行わない。終了同期の要約はCloseの適用後CT・Work状態から作り、承認用targetに含める。Syncで独自に次アクションを決めない。
- 初期は20セクションの存在だけを求め、全欄の確定は求めない。未確認・仮定・該当なし・詳細資料参照を区別する。現在フェーズは提案・見積、契約前、要件定義、基本設計、詳細設計、実装、テスト、移行、保守を案件に合わせて選ぶ。
