# Git 操作手册

## SSH 连接配置

```bash
# 1. 启动 ssh-agent 并加载密钥
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# 2. 测试 SSH 连接（出现 "successfully authenticated" 即成功）
ssh -T git@github.com
```

## 远程仓库

```bash
# 添加远程仓库
git remote add origin git@github.com:shen9220/NEW_Testcase_projects.git

# 拉取远程仓库
git pull origin master

# 推送本地仓库到远程仓库
git push -u origin master

# 删除远程仓库
git remote remove origin

# 查看远程仓库
git remote -v
```

## 分支操作

```bash
# 查看本地分支
git branch

# 查看远程分支
git branch -r

# 查看所有分支
git branch -a

# 切换分支
git checkout branch_name

# 创建分支
git branch branch_name

# 删除分支
git branch -d branch_name

# 合并分支
git merge branch_name
```

## 提交记录

```bash
# 查看提交记录
git log

# 查看当前分支的提交记录（简洁模式）
git log --oneline

# 查看当前分支的提交记录，并显示提交者
git log --oneline --author="shen9220" --date=iso
```
