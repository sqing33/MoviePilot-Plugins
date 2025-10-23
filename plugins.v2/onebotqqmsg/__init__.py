from typing import Any, List, Dict, Tuple
import json
import time

from app.core.config import settings
from app.core.event import eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType
from app.utils.http import RequestUtils


class OneBotQQMsg(_PluginBase):
    plugin_name = "OneBot-QQ消息推送"
    plugin_desc = "将通知事件格式化后使用OneBot协议通过qq小号将消息推送给qq大号。"
    plugin_icon = "OneBotQQMsg_A.png"
    plugin_version = "1.0"
    plugin_author = "sqing"
    author_url = "https://github.com/sqing33"
    plugin_config_prefix = "onebotqqmsg_"
    plugin_order = 14
    auth_level = 1

    _forward_url = None
    _user_id = None
    _access_token = None  # <--- 新增：用于存储 Access Token
    _enabled = False

    _last_forwarded_messages: Dict[str, float] = {}
    _dedup_window_seconds: int = 10  # 去重时间窗口，单位：秒

    def init_plugin(self, config: dict = None):
        """
        初始化插件配置
        """
        if config:
            self._enabled = config.get("enabled")
            self._forward_url = config.get("forward_url")
            self._user_id = config.get('user_id')
            self._access_token = config.get('access_token')  # <--- 新增：从配置中读取 Token

        logger.info(
            f"[{self.plugin_name}] 插件初始化。启用状态: {self._enabled}, URL: {self._forward_url}"
        )

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        # 在表单定义中增加 Token 输入框
        return [{
            'component':
            'VForm',
            'content': [
                {
                    'component':
                    'VRow',
                    'content': [{
                        'component':
                        'VCol',
                        'props': {
                            'cols': 12
                        },
                        'content': [{
                            'component': 'VSwitch',
                            'props': {
                                'model': 'enabled',
                                'label': '启用插件',
                            }
                        }]
                    }]
                },
                {
                    'component':
                    'VRow',
                    'content': [{
                        'component':
                        'VCol',
                        'props': {
                            'cols': 12,
                            'md': 8
                        },
                        'content': [{
                            'component': 'VTextField',
                            'props': {
                                'model': 'forward_url',
                                'label': '转发URL地址',
                                'placeholder': 'http://127.0.0.1:3000/send_private_msg'
                            }
                        }]
                    }, {
                        'component':
                        'VCol',
                        'props': {
                            'cols': 12,
                            'md': 4
                        },
                        'content': [{
                            'component': 'VTextField',
                            'props': {
                                'model': 'user_id',
                                'label': '用户QQ (user_id)',
                                'placeholder': '接收消息的QQ号码'
                            }
                        }]
                    }]
                },
                # --- 新增的 Token 输入框 ---
                {
                    'component': 'VRow',
                    'content': [{
                        'component': 'VCol',
                        'props': {'cols': 12},
                        'content': [{
                            'component': 'VTextField',
                            'props': {
                                'model': 'access_token',
                                'label': '访问令牌 (Access Token)',
                                'placeholder': '如果需要认证，请在此输入 Token'
                            }
                        }]
                    }]
                }
                # --- 新增结束 ---
            ]
        }], {
            "enabled": False,
            "forward_url": "",
            "user_id": "",
            "access_token": ""  # <--- 新增：为 Token 提供默认值
        }

    def get_page(self) -> List[dict]:
        pass

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event):
        """
        向第三方URL发送格式化后的请求
        """
        if not self._enabled or not self._forward_url or not self._user_id:
            return

        if not isinstance(event.event_data, dict):
            logger.error(f"[{self.plugin_name}] event_data 不是一个字典，无法处理。")
            return

        title = event.event_data.get('title', '')
        text = event.event_data.get('text', '')

        if not title and not text:
            return
        
        # 去重逻辑 (保持不变)
        current_time = time.time()
        expired_keys = [
            key for key, ts in self._last_forwarded_messages.items()
            if current_time - ts > self._dedup_window_seconds
        ]
        for key in expired_keys:
            del self._last_forwarded_messages[key]

        message_fingerprint = f"{title}|{text}"
        if message_fingerprint in self._last_forwarded_messages:
            logger.debug(
                f"[{self.plugin_name}] 在 {self._dedup_window_seconds}s 内检测到重复消息，已跳过。Title: '{title}'"
            )
            return
        self._last_forwarded_messages[message_fingerprint] = current_time

        logger.info(f"[{self.plugin_name}] 接收到新通知，准备转发: Title='{title}'")

        try:
            # --- 核心修改部分 ---
            try:
                # 将 user_id 转换为整数
                user_id_int = int(self._user_id)
            except (ValueError, TypeError):
                logger.error(f"[{self.plugin_name}] 配置的 user_id '{self._user_id}' 不是有效的数字，已停止本次转发。")
                return

            # 构建请求体 (Payload)
            formatted_message = f"{title}\n\n{text}" if title and text else title or text
            payload = {
                "user_id": user_id_int,  # <--- 使用整数类型的 user_id
                "message": formatted_message
            }
            # --- 修改结束 ---
            
            logger.debug(
                f"[{self.plugin_name}] 发送的 Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}"
            )

            # 构建请求头 (Headers)
            headers = {}
            if self._access_token:
                headers["Authorization"] = f"Bearer {self._access_token}"
            
            logger.info(
                f"[{self.plugin_name}] 正在发送 POST 请求至: {self._forward_url} ...")
            
            # 发送请求
            ret = RequestUtils(content_type="application/json").post_res(
                self._forward_url, json=payload, headers=headers)

            if ret and ret.status_code == 200:
                logger.info(
                    f"[{self.plugin_name}] 成功转发消息。服务器返回状态码: {ret.status_code}")
            elif ret is not None:
                logger.error(
                    f"[{self.plugin_name}] 转发失败，状态码：{ret.status_code}，返回信息：{ret.text}"
                )
            else:
                logger.error(
                    f"[{self.plugin_name}] 转发失败，未获取到任何返回信息（网络问题或URL无效）。")

        except Exception:
            logger.exception(f"[{self.plugin_name}] 转发请求时发生未知异常！")

    def stop_service(self):
        """
        退出插件
        """
        pass
