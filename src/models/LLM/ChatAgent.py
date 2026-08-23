import asyncio
import os

import requests

# 异步 HTTP 客户端
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# 跨平台文件锁兼容处理
try:
    import fcntl
except ImportError:
    if os.name == 'nt':
        import msvcrt
        class WindowsLock:
            LOCK_EX = 0x1
            LOCK_SH = 0x2
            LOCK_NB = 0x4
            LOCK_UN = 0x8
            
            @staticmethod
            def flock(file, flags):
                try:
                    fd = file.fileno()
                    # 尝试锁定/解锁文件的前 2GB
                    if flags & WindowsLock.LOCK_EX:
                        # LK_RLCK = 0, 锁定指定字节
                        # 注意：msvcrt.locking 在文件指针位置开始锁定
                        # 这里为了简单起见，我们假设锁定整个文件，但 msvcrt 需要指定长度
                        # 且必须将文件指针移到开头才能锁定整个文件，这可能会干扰写入
                        # 因此，作为简单的兼容性修复，如果是在 Windows 上，
                        # 我们暂时只提供一个空实现的占位符，或者仅在不影响写入流的情况下尝试锁定
                        # 考虑到 msvcrt.locking 的复杂性（它是阻塞的且依赖文件指针），
                        # 最安全的无依赖 Windows 修复是提供空操作，避免崩溃。
                        pass
                    elif flags & WindowsLock.LOCK_UN:
                        pass
                except Exception:
                    pass
        fcntl = WindowsLock
    else:
        raise  # 如果不是 Windows 且没有 fcntl，则抛出异常
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tqdm import tqdm
from pathlib import Path

from src.configs.config import (
    REMOTE_URL,
    LOCAL_URL,
    TOKEN,
    BASE_DIR,
    DEFAULT_CHATAGENT_MODEL,
    CHAT_AGENT_WORKERS,
    MOUNT_PAPERS_WORKERS,
)
from src.configs.constants import OUTPUT_DIR

from src.configs.logger import get_logger
from src.models.LLM.utils import encode_image
from src.models.monitor.token_monitor import TokenMonitor

logger = get_logger("src.models.LLM.ChatAgent")
logger.debug(f"ChatAgent pid={os.getpid()}")


class ChatAgent:
    Cost_file = Path(f"{OUTPUT_DIR}/tmp/cost.txt")
    Request_stats_file = Path(f"{OUTPUT_DIR}/tmp/request_stats.txt")
    Record_splitter = "||"
    Record_show_length = 200

    def __init__(
        self,
        token_monitor: TokenMonitor | None = None,
        token: str = TOKEN,
        remote_url: str = REMOTE_URL,
        local_url: str = LOCAL_URL,
    ) -> None:
        self.remote_url = remote_url
        self.token = token
        self.local_url = local_url
        self.header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self.batch_workers = CHAT_AGENT_WORKERS
        self.token_monitor = token_monitor

    @retry(
        stop=stop_after_attempt(15),
        wait=wait_exponential(min=2, max=120),
        retry=retry_if_exception_type((requests.RequestException, requests.Timeout, requests.HTTPError)),
    )
    def remote_chat(
        self,
        text_content: str,
        image_urls: list[str] = None,
        local_images: list[Path] = None,
        temperature: float = 0.5,
        debug: bool = False,
        model=DEFAULT_CHATAGENT_MODEL,
        timeout: int = 120,
    ) -> str:
        """chat with remote LLM, return result.
        
        注意：此方法带有重试机制（最多15次，指数退避），适用于需要高可靠性的场景。
        如果需要快速失败（不重试），请使用 remote_chat_no_retry 方法。
        
        Args:
            text_content: 文本内容
            image_urls: 图片URL列表
            local_images: 本地图片路径列表
            temperature: 温度参数
            debug: 是否返回调试信息
            model: 模型名称
            timeout: 超时时间（秒），默认120秒
        """
        url = self.remote_url
        header = self.header
        # text content
        messages = [{"role": "user", "content": text_content}]
        # insert image urls ----
        if (
            image_urls is not None
            and isinstance(image_urls, list)
            and len(image_urls) > 0
        ):
            image_url_frame = []
            for url_ in image_urls:
                image_url_frame.append(
                    {"type": "image_url", "image_url": {"url": url_}}
                )
            image_message_frame = {"role": "user", "content": image_url_frame}
            messages.append(image_message_frame)

        # insert local images ----
        if (
            local_images is not None
            and isinstance(local_images, list)
            and len(local_images) > 0
        ):
            local_image_frame = []
            for local_image in local_images:
                local_encoded_image = encode_image(local_image)
                local_image_frame.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{local_encoded_image}"
                        },
                    }
                )
            image_message_frame = {"role": "user", "content": local_image_frame}
            messages.append(image_message_frame)

        payload = {"model": model, "messages": messages, "temperature": temperature}

        # 设置超时：连接超时30秒，读取超时由参数控制（默认120秒）
        response = requests.post(url, headers=header, json=payload, timeout=(30, timeout))

        if response.status_code != 200:
            logger.error(
                f"chat response code: {response.status_code}\n{response.text[:500]}, retrying..."
            )
            status_code = 0 if response.status_code != 200 else 1

            # 加了线程锁
            self.update_record(
                status_code=status_code,
                response_code=response.status_code,
                request=text_content,
                response=response.text,
            )
            response.raise_for_status()
        res_text = None
        try:
            res = json.loads(response.text)
            res_text = res["choices"][0]["message"]["content"]
            # 更新总开销
            # token monitor
            if self.token_monitor:
                self.token_monitor.add_token(
                    model=model,
                    input_tokens=res["usage"]["prompt_tokens"],
                    output_tokens=res["usage"]["completion_tokens"],
                )
        except Exception as e:
            res_text = f"Error: {e}"
            logger.error(f"There is an error: {e}")

        # 确保 res_text 不为 None
        if res_text is None:
            res_text = "Error: Empty response"

        status_code = 0 if response.status_code != 200 else 1
        self.update_record(
            status_code=status_code,
            response_code=response.status_code,
            request=text_content or "",
            response=res_text,
        )

        if debug:
            return res_text, response
        return res_text

    def remote_chat_no_retry(
        self,
        text_content: str,
        image_urls: list[str] = None,
        local_images: list[Path] = None,
        temperature: float = 0.5,
        debug: bool = False,
        model=DEFAULT_CHATAGENT_MODEL,
        timeout: int = 60,
    ) -> str:
        """chat with remote LLM without retry mechanism.
        
        此方法不带重试机制，适用于需要快速失败的场景（如 JSON 修复、可选的增强功能等）。
        如果请求失败或超时，会立即返回错误信息而不是重试。
        
        Args:
            text_content: 文本内容
            image_urls: 图片URL列表
            local_images: 本地图片路径列表
            temperature: 温度参数
            debug: 是否返回调试信息
            model: 模型名称
            timeout: 超时时间（秒），默认60秒（比 remote_chat 更短）
            
        Returns:
            LLM 响应文本，失败时返回 "Error: ..." 格式的错误信息
        """
        url = self.remote_url
        header = self.header
        # text content
        messages = [{"role": "user", "content": text_content}]
        # insert image urls ----
        if (
            image_urls is not None
            and isinstance(image_urls, list)
            and len(image_urls) > 0
        ):
            image_url_frame = []
            for url_ in image_urls:
                image_url_frame.append(
                    {"type": "image_url", "image_url": {"url": url_}}
                )
            image_message_frame = {"role": "user", "content": image_url_frame}
            messages.append(image_message_frame)

        # insert local images ----
        if (
            local_images is not None
            and isinstance(local_images, list)
            and len(local_images) > 0
        ):
            local_image_frame = []
            for local_image in local_images:
                local_encoded_image = encode_image(local_image)
                local_image_frame.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{local_encoded_image}"
                        },
                    }
                )
            image_message_frame = {"role": "user", "content": local_image_frame}
            messages.append(image_message_frame)

        payload = {"model": model, "messages": messages, "temperature": temperature}

        try:
            # 设置超时：连接超时10秒，读取超时由参数控制
            response = requests.post(url, headers=header, json=payload, timeout=(10, timeout))

            if response.status_code != 200:
                logger.warning(
                    f"remote_chat_no_retry failed: status={response.status_code}, {response.text[:200]}"
                )
                return f"Error: HTTP {response.status_code}"
            
            res = json.loads(response.text)
            res_text = res["choices"][0]["message"]["content"]
            
            # token monitor
            if self.token_monitor:
                self.token_monitor.add_token(
                    model=model,
                    input_tokens=res["usage"]["prompt_tokens"],
                    output_tokens=res["usage"]["completion_tokens"],
                )
            
            if debug:
                return res_text, response
            return res_text
            
        except requests.Timeout:
            logger.warning(f"remote_chat_no_retry timed out after {timeout}s")
            return f"Error: Timeout after {timeout}s"
        except requests.RequestException as e:
            logger.warning(f"remote_chat_no_retry request failed: {e}")
            return f"Error: Request failed - {e}"
        except Exception as e:
            logger.warning(f"remote_chat_no_retry error: {e}")
            return f"Error: {e}"

    async def async_remote_chat(
        self,
        text_content: str,
        image_urls: list[str] = None,
        local_images: list[Path] = None,
        temperature: float = 0.5,
        model=DEFAULT_CHATAGENT_MODEL,
        timeout: int = 120,
        session: "aiohttp.ClientSession" = None,
    ) -> str:
        """异步版本的 remote_chat，用于高并发场景
        
        Args:
            text_content: 文本内容
            image_urls: 图片URL列表
            local_images: 本地图片路径列表
            temperature: 温度参数
            model: 模型名称
            timeout: 超时时间（秒）
            session: aiohttp 会话，如果为 None 则创建新会话
        
        Returns:
            LLM 响应文本
        """
        if not HAS_AIOHTTP:
            # 回退到同步版本
            return self.remote_chat(
                text_content=text_content,
                image_urls=image_urls,
                local_images=local_images,
                temperature=temperature,
                model=model,
                timeout=timeout,
            )
        
        url = self.remote_url
        headers = self.header
        
        # 构建消息
        messages = [{"role": "user", "content": text_content}]
        
        # 插入图片 URL
        if image_urls and isinstance(image_urls, list) and len(image_urls) > 0:
            image_url_frame = [
                {"type": "image_url", "image_url": {"url": url_}}
                for url_ in image_urls
            ]
            messages.append({"role": "user", "content": image_url_frame})
        
        # 插入本地图片
        if local_images and isinstance(local_images, list) and len(local_images) > 0:
            local_image_frame = []
            for local_image in local_images:
                local_encoded_image = encode_image(local_image)
                local_image_frame.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{local_encoded_image}"}
                })
            messages.append({"role": "user", "content": local_image_frame})
        
        payload = {"model": model, "messages": messages, "temperature": temperature}
        
        # 重试逻辑
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # 如果没有传入 session，创建一个临时的
                if session is None:
                    connector = aiohttp.TCPConnector(limit=0)  # 不限制连接数
                    async with aiohttp.ClientSession(connector=connector) as temp_session:
                        async with temp_session.post(
                            url,
                            headers=headers,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=timeout, connect=30)
                        ) as response:
                            if response.status != 200:
                                text = await response.text()
                                logger.warning(f"异步请求失败 (attempt {attempt + 1}): status={response.status}, {text[:200]}")
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(retry_delay * (2 ** attempt))
                                    continue
                                return f"Error: HTTP {response.status}"
                            
                            res = await response.json()
                            res_text = res["choices"][0]["message"]["content"]
                            
                            # token monitor
                            if self.token_monitor:
                                self.token_monitor.add_token(
                                    model=model,
                                    input_tokens=res["usage"]["prompt_tokens"],
                                    output_tokens=res["usage"]["completion_tokens"],
                                )
                            
                            return res_text
                else:
                    async with session.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=timeout, connect=15)
                    ) as response:
                        if response.status != 200:
                            text = await response.text()
                            logger.warning(f"异步请求失败 (attempt {attempt + 1}): status={response.status}, {text[:200]}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay * (2 ** attempt))
                                continue
                            return f"Error: HTTP {response.status}"
                        
                        res = await response.json()
                        res_text = res["choices"][0]["message"]["content"]
                        
                        # token monitor
                        if self.token_monitor:
                            self.token_monitor.add_token(
                                model=model,
                                input_tokens=res["usage"]["prompt_tokens"],
                                output_tokens=res["usage"]["completion_tokens"],
                            )
                        
                        return res_text
                        
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
                logger.warning(f"异步请求超时 (attempt {attempt + 1})")

                return "Error: Timeout"
            except Exception as e:
                logger.warning(f"异步请求异常 (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
                return f"Error: {e}"
        
        return "Error: Max retries exceeded"

    async def batch_async_remote_chat(
        self,
        prompt_list: list[str],
        temperature: float = 0.5,
        model=DEFAULT_CHATAGENT_MODEL,
        timeout: int = 120,
        max_concurrent: int = None,
        desc: str = "异步批量请求",
    ) -> list[str]:
        """异步批量请求 LLM
        
        Args:
            prompt_list: prompt 列表
            temperature: 温度参数
            model: 模型名称
            timeout: 单个请求超时时间
            max_concurrent: 最大并发数，默认使用 MOUNT_PAPERS_WORKERS
            desc: 进度条描述
        
        Returns:
            响应列表，顺序与输入一致
        """
        if not HAS_AIOHTTP:
            logger.warning("aiohttp 未安装，回退到同步批量请求")
            return self.batch_remote_chat(prompt_list, desc=desc, temperature=temperature)
        
        if max_concurrent is None:
            max_concurrent = MOUNT_PAPERS_WORKERS
        
        results = [""] * len(prompt_list)
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_single(index: int, prompt: str, session: "aiohttp.ClientSession"):
            async with semaphore:
                result = await self.async_remote_chat(
                    text_content=prompt,
                    temperature=temperature,
                    model=model,
                    timeout=timeout,
                    session=session,
                )
                results[index] = result
                return index
        
        # 使用 tqdm 显示进度
        connector = aiohttp.TCPConnector(limit=0)  # 不限制连接数
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                process_single(i, prompt, session)
                for i, prompt in enumerate(prompt_list)
            ]
            
            # 使用 tqdm 包装 as_completed
            for coro in tqdm(
                asyncio.as_completed(tasks),
                total=len(tasks),
                desc=desc,
                dynamic_ncols=True,
            ):
                await coro
        
        return results

    # map chat index
    def __remote_chat(
        self,
        index,
        content,
        temperature: float = 0.5,
        debug: bool = False,
        model=DEFAULT_CHATAGENT_MODEL,
        use_retry: bool = True,
        timeout: int = 120,
    ):
        chat_method = self.remote_chat if use_retry else self.remote_chat_no_retry
        return index, chat_method(
            text_content=content,
            image_urls=None,
            local_images=None,
            temperature=temperature,
            debug=debug,
            model=model,
            timeout=timeout,
        )

    def batch_remote_chat(
        self,
        prompt_l: list[str],
        desc: str = "batch_chating...",
        workers: int = CHAT_AGENT_WORKERS,
        temperature: float = 0.5,
        use_retry: bool = True,
        timeout: int = 120,
    ) -> list[str]:
        """
        开启多线程进行对话
        """
        if workers is None:
            workers = self.batch_workers
        # 创建线程池
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # 提交任务
            future_map = {
                executor.submit(
                    self.__remote_chat,
                    i,
                    prompt_l[i],
                    temperature,
                    False,
                    DEFAULT_CHATAGENT_MODEL,
                    use_retry,
                    timeout,
                ): i
                for i in range(len(prompt_l))
            }
            # 领取任务结果
            res_l = ["no response"] * len(prompt_l)
            for future in tqdm(
                as_completed(future_map),
                desc=desc,
                total=len(future_map),
                dynamic_ncols=True,
            ):
                fallback_index = future_map[future]
                try:
                    i, resp = future.result()
                    res_l[i] = resp
                except Exception as e:
                    logger.warning(
                        f"batch_remote_chat item {fallback_index} failed: {type(e).__name__}: {e}"
                    )
                    res_l[fallback_index] = f"Error: {type(e).__name__}: {e}"
        return res_l

    @classmethod
    def update_record(
        cls, status_code: int, response_code: int, request: str, response: str
    ):
        "维护记录文件"
        # 确保 request 和 response 不为 None
        request = request or ""
        response = response or ""
        content = (
            f"{status_code}{cls.Record_splitter}{response_code}{cls.Record_splitter}{request[: cls.Record_show_length]}{cls.Record_splitter}{response[: cls.Record_show_length]}".replace(
                "\n", ""
            )
            + "\n"
        )
        # 检查文件是否存在
        if not os.path.exists(cls.Request_stats_file):
            parent_dir = Path(cls.Request_stats_file).parent
            parent_dir.mkdir(parents=True, exist_ok=True)
            with open(cls.Request_stats_file, "w", encoding="utf-8") as fw:
                fcntl.flock(fw, fcntl.LOCK_EX)  # 加锁
                fw.write(content)
                logger.info(
                    f"record file {cls.Request_stats_file} did not exist, created and initialized with 0.0"
                )
                fcntl.flock(fw, fcntl.LOCK_UN)
        # 更新开销总计
        try:
            with open(cls.Request_stats_file, "a", encoding="utf-8") as fw:
                fcntl.flock(fw, fcntl.LOCK_EX)
                fw.write(content)
                fcntl.flock(fw, fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"Failed to update cost: {e}")

    def local_chat(self, query, debug=False) -> str:
        """
        调用本地LLM进行推理, 保证端口已开启
        """
        query = """
            <|begin_of_text|><|start_header_id|>system<|end_header_id|>
            You are a helpful AI assistant.<|eot_id|><|start_header_id|>user<|end_header_id|>
            {}<|eot_id|><|start_header_id|>assistant<|end_header_id|>""".format(query)

        payload = json.dumps(
            {
                "prompt": query,
                "temperature": 1.0,
                "max_tokens": 102400,
                "n": 1,
                # 可选的参数在这里：https://github.com/vllm-project/vllm/blob/main/vllm/sampling_params.py
            }
        )
        headers = {"Content-Type": "application/json"}
        res = requests.request("POST", self.local_url, headers=headers, data=payload)
        if res.status_code != 200:
            logger.info("chat response code: {}".format(res.status_code), query[:20])
            return "chat response code: {}".format(res.status_code)
        if debug:
            return res
        return res.json()["text"][0].replace(query, "")

    def __local_chat(self, index, query):
        return index, self.local_chat(query, debug=True)

    def batch_local_chat(self, query_l, worker=16, desc="bach local inferencing..."):
        """
        多线程本地推理
        """
        with ThreadPoolExecutor(max_workers=worker) as executor:
            # 提交任务
            future_l = [
                executor.submit(self.__local_chat, i, query_l[i])
                for i in range(len(query_l))
            ]
            # 领取任务结果
            res_l = ["no response"] * len(query_l)
            for future in tqdm(as_completed(future_l), desc=desc, total=len(future_l)):
                i, resp = future.result()
                res_l[i] = resp
        return res_l

    @staticmethod
    def show_request_stats():
        stats_file = ChatAgent.Request_stats_file
        logger.info(f"stats_file: {stats_file}")

        with stats_file.open("r", encoding="utf-8") as fr:
            succ_count = 0
            total_count = 0
            for line in fr:
                elements = line.strip().split(ChatAgent.Record_splitter)
                succ_count += int(elements[0])
                total_count += 1
            logger.info(f"请求成功率：{round(succ_count / total_count * 100, 2)}%")

    @staticmethod
    def clean_request_stats():
        stats_file = ChatAgent.Request_stats_file
        if stats_file.exists():
            logger.info(f"remove {stats_file}.")


if __name__ == "__main__":
    agent = ChatAgent()
    text_content = "图片里面有什么"

    # result = agent.remote_chat(text_content="今天天气怎么样",  model="gpt-4o")
    # print(result)
    #
    # image_urls = ["https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"]
    # result = agent.remote_chat( text_content=text_content, image_urls=image_urls, temperature=0.5, model="gpt-4o")
    # print(result)

    local_images = [f"{BASE_DIR}/resources/dummy_data/figs/dog_and_girl.jpeg"]
    result = agent.remote_chat(
        text_content=text_content,
        local_images=local_images,
        temperature=0.5,
        model="gpt-4o",
    )
    print(result)

    ChatAgent.show_request_stats()
