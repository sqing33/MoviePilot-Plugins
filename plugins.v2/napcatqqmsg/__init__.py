from typing import Any, List, Dict, Tuple
import json
import time

from app.core.config import settings
from app.core.event import eventmanager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType
from app.utils.http import RequestUtils


class NapCatQQMsg(_PluginBase):
    plugin_name = "NapCat-QQ消息推送"
    plugin_desc = "将通知事件格式化后转发给NapCat，通过qq小号将消息推送给qq大号。"
    plugin_icon = "https://avatars.githubusercontent.com/u/165024194?s=48&v=4"
    plugin_version = "1.0"
    plugin_author = "sqing"
    author_url = "https://github.com/sqing33"
    plugin_config_prefix = "napcatqqmsg_"
    plugin_order = 14
    auth_level = 1

    _forward_url = None
    _user_id = None
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
        # ... (您的 get_form 代码) ...
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
                                'placeholder': '例如：http://127.0.0.1:8080/send'
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
                                'label': '用户ID (user_id)'
                            }
                        }]
                    }]
                },
            ]
        }], {
            "enabled": False,
            "forward_url": "",
            "user_id": ""
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
            # 构建请求体
            formatted_message = f"{title}\n\n{text}" if title and text else title or text
            payload = {
                "user_id": str(self._user_id),
                "message": [{
                    "type": "text",
                    "data": {
                        "text": formatted_message
                    }
                }]
            }
            logger.debug(
                f"[{self.plugin_name}] 发送的 Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}"
            )

            logger.info(
                f"[{self.plugin_name}] 正在发送 POST 请求至: {self._forward_url} ...")
            ret = RequestUtils(content_type="application/json").post_res(
                self._forward_url, json=payload)

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
