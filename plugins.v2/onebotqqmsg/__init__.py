import threading
import requests

from queue import Queue
from time import time, sleep
from typing import Any, List, Dict, Tuple

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType


class LLOneBotMsg(_PluginBase):
    # 插件名称
    plugin_name = "LLOneBot QQ 消息通知"
    # 插件描述
    plugin_desc = "使用 LLOneBot (OneBot v11) 发送 QQ 私聊消息通知。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/botuniverse/onebot-11/main/onebot.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "sqing"
    # 作者主页
    author_url = "https://github.com/google/gemini"
    # 插件配置项ID前缀
    plugin_config_prefix = "llonebotmsg_"
    # 加载顺序
    plugin_order = 26
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _api_url = None
    _token = None
    _qq_user_id = None
    _msgtypes = []

    # 消息处理线程
    processing_thread = None
    # 上次发送时间
    last_send_time = 0
    # 消息队列
    message_queue = Queue()
    # 消息发送间隔（秒）
    send_interval = 5
    # 退出事件
    __event = threading.Event()

    def init_plugin(self, config: dict = None):
        """
        插件初始化
        """
        self.__event.clear()
        if config:
            self._enabled = config.get("enabled")
            self._api_url = config.get("api_url")
            self._token = config.get("token")
            self._qq_user_id = config.get("qq_user_id")
            self._msgtypes = config.get("msgtypes") or []

            # 当所有必要配置都存在时，启动后台发送线程
            if self._enabled and self._api_url and self._token and self._qq_user_id:
                self.processing_thread = threading.Thread(target=self.process_queue)
                self.processing_thread.daemon = True
                self.processing_thread.start()

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled and bool(self._api_url and self._token and self._qq_user_id)

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，返回页面配置和数据结构
        """
        # 遍历 NotificationType 枚举，生成消息类型选项
        msg_type_options = []
        for item in NotificationType:
            msg_type_options.append({
                "title": item.value,
                "value": item.name
            })
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'api_url',
                                            'label': 'LLOneBot接口地址',
                                            'placeholder': 'http://192.168.1.100:3000',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'qq_user_id',
                                            'label': '接收消息的QQ号',
                                            'placeholder': '填写接收消息的QQ号',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'token',
                                            'label': 'Bearer Token',
                                            'placeholder': '填写LLOneBot的访问令牌',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'model': 'msgtypes',
                                            'label': '启用的消息类型',
                                            'items': msg_type_options
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                ]
            }
        ], {
            "enabled": False,
            'api_url': 'https://qq.916337.xyz',
            'token': '',
            'qq_user_id': '',
            'msgtypes': []
        }

    def get_page(self) -> List[dict]:
        pass

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event: Event):
        """
        消息发送事件，将消息加入队列
        """
        if not self.get_state() or not event.event_data:
            return

        msg_body = event.event_data
        # 验证消息的有效性
        if not msg_body.get("title") and not msg_body.get("text"):
            logger.warn("标题和内容不能同时为空")
            return

        # 将消息加入队列
        self.message_queue.put(msg_body)
        logger.info("QQ消息已加入队列等待发送")

    def process_queue(self):
        """
        处理队列中的消息，按间隔时间发送
        """
        while not self.__event.is_set():
            try:
                # 从队列中获取消息，如果队列为空会阻塞等待
                msg_body = self.message_queue.get()

                # 检查是否满足发送间隔时间
                current_time = time()
                time_since_last_send = current_time - self.last_send_time
                if time_since_last_send < self.send_interval:
                    sleep(self.send_interval - time_since_last_send)

                # 处理消息内容
                msg_type: NotificationType = msg_body.get("type")
                title = msg_body.get("title")
                text = msg_body.get("text")

                # 检查消息类型是否已启用
                if msg_type and self._msgtypes and msg_type.name not in self._msgtypes:
                    logger.info(f"消息类型 {msg_type.value} 未开启，跳过发送")
                    self.message_queue.task_done()
                    continue

                # 格式化最终发送的消息
                # 如果有标题，格式为【标题】\n内容，否则直接为内容
                final_message = ""
                if title:
                    final_message += f"【{title}】\n"
                final_message += text if text else ""
                
                if not final_message.strip():
                    logger.warn("要发送的最终消息内容为空，跳过")
                    self.message_queue.task_done()
                    continue

                # 拼接完整的请求URL
                api_endpoint = f"{self._api_url.rstrip('/')}/send_private_msg"
                
                # 准备请求头和请求体
                headers = {
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "user_id": int(self._qq_user_id),
                    "message": final_message
                }

                # 尝试发送消息
                try:
                    response = requests.post(api_endpoint, json=payload, headers=headers, timeout=10)
                    # 检查HTTP响应状态码，如果不是2xx则会抛出异常
                    response.raise_for_status()
                    logger.info("LLOneBot QQ消息发送成功！")
                except Exception as msg_e:
                    logger.error(f"LLOneBot QQ消息发送失败: {str(msg_e)}")

                # 更新最后发送时间并标记任务完成
                self.last_send_time = time()
                self.message_queue.task_done()

            except Exception as e:
                logger.error(f"消息处理线程出现未知错误: {str(e)}")
                # 出现异常时暂停一下，避免快速循环刷日志
                sleep(self.send_interval)

    def stop_service(self):
        """
        退出插件
        """
        self.__event.set()
        # 添加一个空消息到队列，以解除 process_queue 中 get() 方法的阻塞
        self.message_queue.put(None)
        logger.info("LLOneBot QQ消息通知插件已停止")
