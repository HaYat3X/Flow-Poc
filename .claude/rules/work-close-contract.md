# Close判断と終了同期の契約

## 責務と入口

Closeは終了可否、候補の採否、残件の行き先、依頼全体に対する次アクション、引継ぎ内容を判断する。Syncは保存された承認済み内容だけを適用し、採否・終了状態・次アクションを独自に変更しない。

Syncの入口は `input`（入力追加）、`decision`（途中の承認済み判断の反映）、`close`（終了判断の適用）の3種。終了判断が存在するだけでinput/decisionをcloseへ切り替えない。Closeの案内に従う対象Workの終了同期依頼、または明示されたClose→Sync一括依頼だけがcloseに該当する。候補ゼロでもcloseで状態・台帳を確定する。

## 終了判断の保存

Workの `終了判断.md` に次を保存する。

- workflow_schema、document_type: work_close_decision、project_id、work_id、request_id。
- close_id: W-xxxx-Cnn（Work内で再利用しない）、decision_status: draft / approved / applying / synced / invalidated。
- final_status: completed / cancelled / on_hold / handoff。
- request_completion: satisfied / unsatisfied / unknown（依頼の終了条件の判定）。
- plan_revision: 判断対象の計画改訂番号。計画なしの緊急例外では0とし、例外根拠を記載する。
- remaining_planned_work: 終了同期後に残る計画済みWork候補数。進行計画の今回始めるWorkのうち未着手・開始済みの行（旧形式ではWork候補のplanned行）。並行Work・依存待ちも含める。今回の終了Workは除く。
- unplanned_remaining: WBSに未完了の作業パッケージ（子のない行）が残り、進行計画の残りの行で扱われていない場合にtrue（旧形式ではplan_coverage: partial）。
- unplanned_remaining: true / false、plan_changed: true / false、continuation_blocked: true / false。
- next_action: continue_work / plan_remaining / replan / request_close / resolve_blocker、next_target、next_reason。
- approved_by、approved_at、updated_by、updated_at。draftでは承認情報はnone。適用完了時だけsynced_atを記録する。

必須本文は「完了条件の判定」「候補の処理」「残件の行き先」「依頼全体と次アクション」「承認対象の版」。完了条件は条件ごとにsatisfied/unsatisfied/not_applicableと根拠を記載する。候補の処理には全候補IDと反映/見送り/保留/残作業化、理由、反映先または行き先を記載する。候補ゼロはなしと明記する。引継ぎ.mdを承認対象へ含める。

## 部分計画と次アクション

依頼の終了条件と計画の消化は別に判断する。初期Planは部分計画を許可し、未計画の範囲・具体化条件を残す。優先順は次の通り。

1. 判断不足・行き先のない残件・継続阻害がある → resolve_blocker。
2. 依頼の終了条件がsatisfiedで、他の計画済み・並行Workや未計画範囲が残らない → request_close。
3. 前提・依存・方針・終了条件の見直しが必要 → replan。
4. 開始可能な計画済み候補が残る → continue_work（next_targetに進行計画の行のP-ID、並行Workの継続ならW-ID。既存W-IDを重複開始しない）。
5. 計画済み候補がなく、未計画範囲が残る → plan_remaining（next_targetにRQ-IDと次の区切りで扱うP-ID。Planで進行計画を書き直し、区切り承認を受ける）。
6. 終了条件がunsatisfiedで計画済み候補も未計画範囲の記録もない → plan_remainingとして不足を明示し、残りの作業を洗い出す。

request_completionがunknownならresolve_blocker。待ち状態しか残らない場合もcontinuation_blockedとして具体的な解消条件を残す。計画を変更せず継続するWorkに追加のPlanレビューを要求しない。plan_remainingは承認済み部分計画の拡張であり、単なる消化を理由にneeds_revisionへ落とさない。replanの場合だけ依頼・計画をneeds_revisionへ揃える。

## 承認対象の版と適用後内容

「承認対象の版」は次の表を使う。

| 種別 | 参照 | 適用前SHA256 | 適用後SHA256 | 適用後内容 |
| --- | --- | --- | --- | --- |

- 種別はsourceまたはtarget。参照はルート相対パス、Work内は `work:作業内容.md` のように記載する。絶対パス・親への脱出・外部URLは使わない。
- sourceは判断根拠。適用前後は同じSHA256、適用後内容はnone。対象の入力要約、追加原本、引継ぎ、成果・根拠を含める。外部参照は版・コミットを固定した根拠記録をWork内に残し、その記録もsourceに含める。
- targetは変更対象。適用前は現在のSHA256、新規はmissing。適用後はCloseで作った承認用ファイルのSHA256。廃止等で削除する正本は適用後missing、適用後内容noneとして明示する。Contextの詳細分離ではメインを削除しない。適用後内容は `work:終了反映案/…` で指定する。適用後内容自体も承認したSHA256に一致する必要がある。
- Workの作業内容・入力一覧・作業メモ・反映候補、関連依頼・計画、Context、関係する索引・現在地・更新履歴を漏れなくsourceまたはtargetへ登録する。未変更の正本も判断に使用したものはsourceとして監視する。索引は依頼一覧・入力資料一覧・Context一覧・トレーサビリティ・リポジトリ情報・ナレッジ一覧で、存在するものは変更しない場合もsourceとして登録する（検査ツールが必須とする）。依頼承認記録・計画承認記録・Workの承認記録も存在すればsourceとして登録する。Workの承認記録に提示中の承認が残っている間はCloseしない（version-tableが列挙し、verify-closeが確認する）。
- 版表は `project_workflow_check.py version-table --root . --work <Work相対パス> --target <参照>=work:終了反映案/<ファイル> --delete <参照>` で雛形を作る。必須の参照と現在のSHA256を列挙し、`--target` に指定した参照は承認用内容のSHA256でtargetにする。`--target`・`--delete` は複数指定でき、SHA256を手で計算・転記しない。「要対応」が出た場合は不足を解消してから版表へ貼る。
- Contextの1・12・17・20と分離済みセクションの要約は、適用後のCT・Work・Context詳細から更新要否を確認する。差分があればメインもtargetに含める。候補ゼロでも進捗・次アクションの変化を要約へ反映する。文字数超過時の詳細分離・参照修正も承認用targetに含め、Syncで独自に本文や判断を追加しない。
- Close承認後の追加作業・入力・判断・承認用ファイルの変更は承認を無効化する。終了判断本文自体も承認時SHA256を `終了判断承認.sha256` に保存し、Syncは適用前に照合する。この封印は承認完了後に一度だけ作成し、Syncが再封印してはならない。
- SHA256はファイルのバイト列で算出する。終了判断自体はdecision_status、synced_at、updated_at、updated_by以外の承認済み部分を封印する（検査ツールのseal-closeを使う）。

### 検証が保証する範囲

- 終了同期の検証が保証するのは、版表に登録したファイルが承認時の版から承認済みの適用後版へ変わったこと、Workの入力・成果に未登録の追加がないことだけである。版表にないファイルへの変更は検出できない。このため上記の索引と関連正本を漏れなく登録し、Syncは版表のtarget以外へ書き込まない。
- 承認封印は承認後の改変を検出する仕組みであり、承認者の証明ではない。封印ファイルはツールが作る通常のハッシュ値で、封印を削除して作り直せば検出できない。approved_byは承認の発言者とし、承認の事実は利用者またはPMの発言と更新履歴で追跡する。封印の作り直しは新しいclose_idでの再承認だけとし、同じclose_idの封印を削除・再作成しない。

## 終了同期

1. 終了判断・封印・入力・結果・正本を再読し、`project_workflow_check.py verify-close --root . --work <Work相対パス> --phase before` を実行する。承認済みで全source/targetが適用前版に一致する場合だけ進む。
2. decision_statusをapplyingにし、承認されたtargetを適用する。候補処理履歴へ同期済みと反映先を残す内容は、承認用ファイルに含める。採否や次アクションを追加判断しない。
3. completedではWorkフォルダを完了へ移動し、関連参照を承認済み適用後内容に合わせる。Work文書の中のWork自身へのパスはWorkからの相対パスなので書き換えない。Work文書（承認用内容を含む）にWork自身をルートからのパスで書いた箇所があれば、verify-closeが移動で切れるパスとして止める。移動後もwork:参照は同じWorkを指す。
4. `verify-close --phase after` で全sourceが不変、全targetが適用後版であることを確認する。承認されたfinal_statusと全Work記録・台帳の一致、候補の同期済み/同期不要を確認する。
5. decision_statusをsynced、synced_atを実日時へ更新して共通検査を実行する。保存済みnext_action・対象・理由を案内する。Closeの再依頼や通常のPlanレビューを追加しない。

途中で停止した場合はapplyingのまま不足を報告する。`verify-close --phase resume` が成功したときだけ、適用前のtargetを適用し、適用後のtargetは再適用しない。source変更、想定外のtarget、承認用内容の改変、封印不一致ならCloseへ戻す。発行IDは承認用内容で予約し、再実行でIDを再発行しない。syncedの同一close_idを再同期する依頼は適用済みと報告し、意味判断や書込みを繰り返さない。

承認用差分と版表は履歴として保持する。通常検査はsynced判断の過去sourceと現在の案件Contextを再比較しない。後続Workによる正当なContext更新で過去Workを無効にしない。アーカイブで依頼・計画を移す場合も過去の承認内容と封印を変更せず、移動先対応はトレーサビリティ・更新履歴に記録する。

再判断では旧終了判断・引継ぎ・封印・終了反映案を `終了判断履歴/<旧close_id>/` に保存し、旧参照先からの対応を残す。新しいclose_idの承認用ファイルと封印を作る。過去の封印を上書きして新しい承認に見せない。
