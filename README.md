# 安装文档

## 推荐环境
- **操作系统**: Linux (Ubuntu)

## 前置依赖
安装以下工具：
```bash
sudo apt update
sudo apt install -y uv npm git
sudo snap install deno
```
> **注意**  
> 本项目的 `langchain_ark` 库为专门开发的版本，如果您不使用uv，请从./src/whl/中获取这个库的whl文件
## 获取代码
```bash
git clone https://github.com/Fun10165/model-server.git
cd model-server
```

## 安装依赖
```bash
uv sync
```

## 配置文件
1. 复制默认配置文件：
```bash
cp .env.example .env
```
> **注意**  
> 默认提供的 `api_key` 仅用于测试，请勿滥用

## 端口配置
- 服务器默认监听：`0.0.0.0:8443` (HTTP协议)
- **访问方式**：
  - 有公网IP：直接通过 `http://<您的公网IP>:8443` 访问
  - 无公网IP：
    1. 通过 CloudNS 等服务获取域名
    2. 使用 Cloudflare + Cloudflare Tunnel 实现 DNS 解析和隧道服务

## 启动服务
```bash
./run.sh
```

## 验证运行
访问 API 文档确认服务状态：  
`http://127.0.0.1:8443/docs`

## 配置修改
修改讯飞星辰工具中的访问路径：
- 将默认地址 `model-server.fun10165.ip-ddns.com` 
- 替换为 **您的域名地址**
```diff
- model-server.fun10165.ip-ddns.com
+ your-custom-domain.com
```

> **关键提示**  
> 完成所有配置后，请重启服务使更改生效
```bash
# 停止服务
Ctrl+C

# 重新启动
./run.sh