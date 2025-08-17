#!/bin/bash

# 服务器健康检查脚本
# 测试基础连接性和API功能

# 配置部分
SERVER_URL="http://127.0.0.1:8443"
API_ENDPOINT="$SERVER_URL/api/v1/mcp/execute"
TIMEOUT_SEC=60  # 超时时间

# 输出分隔符
SEPARATOR="========================================"

# 函数：带错误处理的CURL请求
run_curl() {
    local description=$1
    local method=$2
    local url=$3
    local data=$4
    
    echo -e "\n${SEPARATOR}"
    echo "测试: $description"
    echo "URL: $url"
    
    local curl_cmd="curl -s -S -X '$method' -H 'accept: application/json'"
    
    # 添加POST数据和header
    if [[ "$method" == "POST" ]]; then
        curl_cmd+=" -H 'Content-Type: application/json' -d '$data'"
    fi
    
    curl_cmd+=" --connect-timeout $TIMEOUT_SEC -w '\n状态码: %{http_code}\n' '$url'"
    
    # 执行命令并捕获输出
    echo "执行命令: ${curl_cmd//$data/*****}"  # 隐藏敏感数据
    local output=$(eval "$curl_cmd" 2>&1)
    local exit_code=$?
    
    # 检查结果
    if [ $exit_code -ne 0 ]; then
        echo -e "\n[错误] 请求失败! (退出码: $exit_code)"
        echo "错误详情:"
        echo "$output"
        return 1
    else
        echo -e "$output"
        # 检查HTTP状态码
        local http_code=$(echo "$output" | awk '/状态码:/ {print $2}')
        if [[ "$http_code" != 2* ]]; then
            echo "[警告] 非成功状态码: $http_code"
            return 2
        else
            echo "[成功] 请求返回状态码: $http_code"
            return 0
        fi
    fi
}

# 主测试流程
echo "开始服务器健康检查 $(date)"
echo $SEPARATOR

# 测试1: 基础GET请求
run_curl "基础连接测试" "GET" "$SERVER_URL" ""
test1_result=$?

# 测试2: API POST请求
run_curl "API功能测试" "POST" "$API_ENDPOINT" '{"INPUT": "Hello!", "polling": false}'
test2_result=$?

# 最终总结
echo -e "\n${SEPARATOR}"
echo "健康检查汇总:"
echo "基础连接测试: $([ $test1_result -eq 0 ] && echo "通过" || echo "失败")"
echo "API功能测试:  $([ $test2_result -eq 0 ] && echo "通过" || echo "失败")"

if [ $test1_result -ne 0 ] || [ $test2_result -ne 0 ]; then
    echo -e "\n[!] 健康检查未通过! 请检查服务器状态"
    exit 1
else
    echo -e "\n[√] 所有测试通过! 服务器状态正常"
    exit 0
fi
