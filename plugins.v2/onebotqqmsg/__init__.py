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
    plugin_desc = "将通知事件格式化后使用OneBot通过qq小号将消息推送给qq大号。"
    plugin_icon = "OneBotQQMsg_A.png"
    plugin_version = "1.0"
    plugin_author = "sqing"
    author_url = "https://github.com/sqing33"
    plugin_config_prefix = "onebotqqmsg_"
    plugin_order = 14
    auth_level = 1

    _forward_url = None
    _user_id = None
    _access_token = None
    _enabled = False

    _last_forwarded_messages: Dict[str, float] = {}
    _dedup_window_seconds: int = 10

    def init_plugin(self, config: dict = None):
        """
        初始化插件配置
        """
        if config:
            self._enabled = config.get("enabled")
            self._forward_url = config.get("forward_url")
            self._user_id = config.get('user_id')
            self._access_token = config.get('access_token')

        logger.info(
            f"[{self.plugin_name}] 插件初始化。启用状态: {self._enabled}, URL: {self._forward_url}"
        )

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件API，提供测试发送功能
        """
        return [{
            "path": "/test_send",
            "method": "GET",
            "func": self.test_send_api,
            "desc": "发送测试消息"
        }]

    def test_send_api(self) -> Dict[str, Any]:
        """
        测试发送API的实现
        """
        # 即使插件未启用，也允许测试
        if not self._forward_url or not self._user_id:
            return {"code": -1, "msg": "请先配置转发URL和用户QQ并保存！"}

        success, msg = self._send_message(
            title="NapCat测试",
            text="这是一条测试消息，收到此消息说明NapCat消息推送配置成功！"
        )
        return {"code": 0 if success else -1, "msg": msg}

    def _send_message(self, title: str, text: str) -> Tuple[bool, str]:
        """
        内部核心发送方法
        :return: (是否成功, 返回信息)
        """
        if not self._forward_url or not self._user_id:
            return False, "未配置转发URL or 用户QQ"

        try:
            try:
                user_id_int = int(self._user_id)
            except (ValueError, TypeError):
                err_msg = f"配置的 user_id '{self._user_id}' 不是有效的数字"
                logger.error(f"[{self.plugin_name}] {err_msg}")
                return False, err_msg

            formatted_message = f"{title}\n\n{text}" if title and text else title or text
            payload = {
                "user_id": user_id_int,
                "message": formatted_message
            }

            headers = {}
            if self._access_token:
                headers["Authorization"] = f"Bearer {self._access_token}"

            logger.info(f"[{self.plugin_name}] 正在发送 POST 请求至: {self._forward_url} ...")
            ret = RequestUtils(content_type="application/json").post_res(
                self._forward_url, json=payload, headers=headers)

            if ret and ret.status_code == 200:
                resp_data = ret.json()
                # OneBot v11 成功通常返回 retcode 0
                if resp_data.get('retcode') == 0: 
                     logger.info(f"[{self.plugin_name}] 消息发送成功。")
                     return True, "消息发送成功"
                else:
                     logger.warning(f"[{self.plugin_name}] 服务器返回 200 但 retcode 不为 0: {resp_data}")
                     return False, f"发送失败，API返回: {resp_data}"

            elif ret is not None:
                err_msg = f"发送失败，状态码：{ret.status_code}，响应：{ret.text}"
                logger.error(f"[{self.plugin_name}] {err_msg}")
                return False, err_msg
            else:
                err_msg = "发送失败，网络请求无响应（请检查URL是否正确）"
                logger.error(f"[{self.plugin_name}] {err_msg}")
                return False, err_msg

        except Exception as e:
            err_msg = f"发送请求时发生异常: {str(e)}"
            logger.exception(f"[{self.plugin_name}] {err_msg}")
            return False, err_msg

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [{
            'component':
            'VForm',
            'content': [
                {
                    'component': 'VRow',
                    'content': [{
                        'component': 'VCol',
                        'props': {'cols': 12},
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
                    'component': 'VRow',
                    'content': [{
                        'component': 'VCol',
                        'props': {'cols': 12, 'md': 8},
                        'content': [{
                            'component': 'VTextField',
                            'props': {
                                'model': 'forward_url',
                                'label': '转发URL地址',
                                'placeholder': 'http://127.0.0.1:3000/send_private_msg'
                            }
                        }]
                    }, {
                        'component': 'VCol',
                        'props': {'cols': 12, 'md': 4},
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
                },
                # --- 新增：测试按钮 ---
                # 注意：按钮能否交互取决于前端框架是否支持在表单中直接绑定API调用
                {
                    'component': 'VRow',
                    'content': [{
                        'component': 'VCol',
                        'props': {'cols': 12},
                        'content': [
                            {
                                'component': 'VAlert',
                                'props': {'type': 'info', 'variant': 'tonal', 'text': '修改配置后请先保存，然后再点击测试按钮。'}
                            },
                            # 尝试添加一个指向我们刚创建的API的按钮
                            # 如果您使用的框架支持特定组件来调用插件API，请替换此处的 VBtn
                            {
                                'component': 'VBtn',
                                'props': {
                                    'color': 'primary',
                                    'text': '发送测试消息',
                                    'class': 'mt-2',
                                    # 某些框架实现可能支持以此方式绑定点击事件调用插件API
                                    # 如果点击无效，说明当前前端不支持此方式，请使用Apifox调用 /api/plugins/napcatqqmsg/test_send
                                    'onClick': 'api:/napcatqqmsg/test_send' 
                                }
                            }
                        ]
                    }]
                }
                # --- 新增结束 ---
            ]
        }], {
            "enabled": False,
            "forward_url": "",
            "user_id": "",
            "access_token": ""
        }

    def get_page(self) -> List[dict]:
        pass

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event):
        """
        向第三方URL发送格式化后的请求
        """
        if not self._enabled:
            return

        if not isinstance(event.event_data, dict):
            return

        title = event.event_data.get('title', '')
        text = event.event_data.get('text', '')

        if not title and not text:
            return
        
        # 去重逻辑
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

        # 调用内部发送方法
        self._send_message(title, text)

    def stop_service(self):
        """
        退出插件
        """
        pass
