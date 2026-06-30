# 项目环境说明
- Python虚拟环境在 .venv 文件夹，每次运行脚本前先激活：.venv\Scripts\activate
- ERA5 API Key已在本机 ~/.cdsapirc 配置；不要把真实 key 提交到 GitHub
- 所有Python脚本在 scripts/ 目录下
- 数据存放在 data/ 目录下

# 每次启动必须做的事
1. 确认.venv存在，不存在则创建并安装requirements.txt
2. 确认~/.cdsapirc存在，不存在则按本机私有配置写入ERA5配置
3. 工作目录始终在项目根目录
