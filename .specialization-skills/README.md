# 特化Skillの保管場所

このディレクトリのSkillは非アクティブです。共通Skillや通常の自然言語依頼から、探索・提案・自動実行しません。

利用者がSkill名を指定して配置を依頼した場合に限り、対象のSkillディレクトリ一式を `.agents/skills/` へ配置します。配置後は `.tools/project_workflow_check.py sync-skills` でClaude Code用の `.claude/skills/` にも複製します。実行時はその都度Skill名を明示指定します（Codexは `$skill-name`、Claude Code・GitHub Copilotは `/skill-name`）。

特化Skillを使っても、Contextの確定、Work・依頼の終了、アーカイブは自動では行いません。
