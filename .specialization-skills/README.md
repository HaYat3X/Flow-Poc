# 特化Skillの保管場所

このディレクトリのSkillは非アクティブです。共通Skillや通常の自然言語依頼から、探索・提案・自動実行しません。

利用者がSkill名を指定して配置を依頼した場合に限り、次の順で配置します。

1. `.specialization-skills/<skill名>/` を `.agents/skills/<skill名>/` へ移動します（保管場所には残しません）。
2. `.tools/project_workflow_check.py sync-skills` で Claude Code用の `.claude/skills/` へ複製します。`.claude/skills/` へ直接置きません。
3. 共通検査で一致を確かめます。
実行時はその都度Skill名を明示指定します（Codexは `$skill-name`、Claude Code・GitHub Copilotは `/skill-name`）。

特化Skillを使っても、Contextの確定、Work・依頼の終了、アーカイブは自動では行いません。
