# git@github.com: Permission denied (publickey).
fatal: 无法读取远程仓库。请确认您有访问权限，并且仓库存在。

## 原因
当前 Git 远程仓库使用 SSH 协议，但本地 SSH 公钥未上传至 GitHub，或者 SSH 客户端配置有误，导致认证失败。

---

## 解决步骤

### 1. 检查远程地址是否使用 SSH
- 在项目根目录执行 `git remote -v`，确认 `origin` 地址开头为 `git@github.com:...`。
- 如果你**没有**配置过 SSH 密钥，最简单的做法是改用 HTTPS 协议（参考“方案 B”）。

### 2. 方案 A：配置 SSH 密钥并上传至 GitHub

#### 2.1 查看本地是否已有 SSH 密钥
- 检查 `~/.ssh` 目录下是否存在 `id_ed25519` 和 `id_ed25519.pub`，或 `id_rsa` 和 `id_rsa.pub`。
- 若不存在，则生成新的密钥（推荐 ed25519 算法）。

#### 2.2 生成新密钥（如需要）
- 运行 `ssh-keygen -t ed25519 -C "你的GitHub邮箱"`，一路回车使用默认路径，可设空密码。

#### 2.3 将公钥添加到 GitHub
- 复制公钥文件内容（`~/.ssh/id_ed25519.pub`，或用命令 `cat ~/.ssh/id_ed25519.pub`）。
- 登录 GitHub → 点击右上角头像 → Settings → SSH and GPG keys → New SSH key。
- 粘贴公钥并保存。

#### 2.4 测试 SSH 连接
- 运行 `ssh -T git@github.com`，若提示 “You've successfully authenticated” 即表明成功。

#### 2.5 重新推送
- 执行 `git push -u origin main`。

### 3. 方案 B：切换为 HTTPS 协议（免配置 SSH）
- 修改远程地址为 HTTPS 格式：`git remote set-url origin https://github.com/用户名/仓库名.git`
- 推送时会要求输入用户名和密码，密码处需使用 **个人访问令牌（Personal Access Token）**，而非 GitHub 账号密码。
- 生成令牌：GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → 勾选 `repo` 权限 → 生成并复制。

### 4. 其他排查点
- 确保本地 SSH Agent 正在运行且已加载私钥（`ssh-add -l` 检查）。
- 如果之前使用过多个 GitHub 账号，检查 SSH 配置文件是否正确指定了 Host 与 IdentityFile。
- Windows 用户若使用 OpenSSH，确保服务已启动，或考虑使用 Git Bash 环境。

---

## 推荐策略
- 若项目**仅个人使用**且希望快速解决，建议直接改用 HTTPS + 令牌方案。
- 若需频繁推送或多人协作，推荐花费 2 分钟配置 SSH 密钥，一劳永逸。