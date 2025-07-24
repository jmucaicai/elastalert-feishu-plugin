#! /usr/bin/env python
# -*- coding: utf-8 -*-

import json
import requests
import time
from elastalert.alerts import Alerter
from elastalert.util import elastalert_logger, EAException
from requests.exceptions import RequestException

class FeishuAlert(Alerter):

    required_options = frozenset(['feishualert_botid', "feishualert_title", "feishualert_body"])

    def __init__(self, rule):
        super(FeishuAlert, self).__init__(rule)
        self.url = self.rule.get("feishualert_url", "https://open.feishu.cn/open-apis/bot/v2/hook/")
        self.bot_id = self.rule.get("feishualert_botid", "")
        self.title = self.rule.get("feishualert_title", "")
        self.body = self.rule.get("feishualert_body", "")
        self.skip = self.rule.get("feishualert_skip", {})
        if not all([self.bot_id, self.title, self.body]):
            raise EAException("Configure botid|title|body is invalid")

    def get_info(self):
        return {"type": "FeishuAlert"}

    def get_rule(self):
        return self.rule

    def _flatten_dict(self, d, parent_key='', sep='.'):
        """将嵌套字典展平为单层字典，处理 host.name 这种情况"""
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(self._flatten_dict(v, new_key, sep))
            else:
                items[new_key] = v
        return items

    def _safe_format(self, text, data):
        """安全的字符串格式化，处理缺失字段"""
        try:
            # 先尝试标准格式化
            return text.format(**data)
        except KeyError as e:
            # 缺失字段时进行手动替换
            for key, value in data.items():
                placeholder = "{" + key + "}"
                text = text.replace(placeholder, str(value))
            return text
        except Exception as e:
            elastalert_logger.warning(f"Format error: {str(e)}")
            return text

    def alert(self, matches):
        # 静默时段检查
        now = time.strftime("%H:%M:%S", time.localtime())
        if "start" in self.skip and "end" in self.skip:
            if self.skip["start"] <= now <= self.skip["end"]:
                elastalert_logger.info("Skip match in silence time...")
                return

        # 准备基础数据
        alert_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        merge_data = {
            "feishualert_title": self.title,
            "feishualert_time": alert_time,
            **self.rule
        }

        # 处理匹配数据
        if matches:
            # 展平嵌套结构（处理 host.name 等情况）
            flat_match = self._flatten_dict(matches[0])
            
            # 特殊处理常见字段
            flat_match.setdefault('host.name', flat_match.get('host_name', 'N/A'))
            flat_match.setdefault('@timestamp', flat_match.get('timestamp', alert_time))
            
            merge_data.update(flat_match)

        # 生成消息内容
        try:
            formatted_body = self._safe_format(self.body, merge_data)
        except Exception as e:
            formatted_body = f"?? Format error: {str(e)}\nRaw message:\n{self.body}"
            elastalert_logger.error(f"Failed to format alert: {str(e)}")

        # 构建飞书消息
        message = {
            "msg_type": "text",
            "content": {
                "text": formatted_body
            }
        }

        # 发送请求
        try:
            response = requests.post(
                url=f"{self.url}{self.bot_id}",
                json=message,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
        except RequestException as e:
            raise EAException(f"Feishu request failed: {str(e)}")
