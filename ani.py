import asyncio, aiohttp, sys, aiofiles, json, os
from loguru import logger

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss:SSS}</green> | <level>{level: <8}</level> | <green>{name}:{function}:{line}</green> - <level>{message}</level>",
    level="DEBUG"
)

ani = "https://openani.an-i.workers.dev/"
headers = {
    'origin': ani,
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    "Content-Type": "application/json"
}
data = '{"password":"null"}'
max_retries = 5
retry_delay = 2
strm_directory = '/root/strm'  # strm 文件保存路径
os.makedirs(strm_directory, exist_ok=True)

async def Get_List():
    retries = 0
    async with aiohttp.ClientSession() as session:
        while retries < max_retries:
            try:
                async with session.post(ani, headers=headers, data=data) as response:
                    if response.status == 200:
                        response_data = await response.text()
                        return json.loads(response_data)
                    elif response.status == 500:
                        logger.error(f"服务器错误，状态码: {response.status}。重试 {retries + 1}/{max_retries} 次。")
                        retries += 1
                        await asyncio.sleep(10)
                    else:
                        response_text = await response.text()
                        logger.error(f"请求失败，状态码: {response.status}，响应内容: {response_text}")
                        return None
            except Exception as e:
                logger.error(f"请求失败，异常信息: {e}")
                return None
        logger.error("重试次数已达上限，放弃请求。")
        return None

async def File_Exists_And_Matches(video_url, filename):
    if os.path.exists(filename):
        async with aiofiles.open(filename, mode='r', encoding='utf-8') as f:
            existing_content = await f.read()
            if existing_content.strip() == f"{video_url}?d=true":
                logger.debug(f"文件 {filename} 已存在且内容匹配，跳过写入")
                return True
    return False

async def STRM_File(video_url, name, folder_path):
    name_without_extension = os.path.splitext(name)[0]
    target_folder = os.path.join(strm_directory, folder_path)
    os.makedirs(target_folder, exist_ok=True)
    strm_filename = os.path.join(target_folder, f"{name_without_extension}.strm")
    if not await File_Exists_And_Matches(video_url, strm_filename):
        try:
            async with aiofiles.open(strm_filename, mode='w', encoding='utf-8') as f:
                await f.write(f"{video_url}?d=true")
            logger.info(f"成功创建 strm 文件: {strm_filename}")
        except Exception as e:
            logger.error(f"写入 strm 文件失败，异常信息: {e}")
    else:
        logger.debug(f"跳过重复的文件 {strm_filename}。")

async def Extract_Names_and_Post(files, current_path=""):
    for file in files:
        name = file["name"]
        mime_type = file["mimeType"]
        full_path = os.path.join(current_path, name)
        if "folder" in mime_type:
            logger.info(f"发现文件夹: {full_path}")
            os.makedirs(os.path.join(strm_directory, full_path), exist_ok=True)
            folder_files = await Get_Names_from_Folder(f"{ani}{full_path}/")
            await Extract_Names_and_Post(folder_files, full_path)
        elif "video" in mime_type:
            video_url = f"{ani}{full_path}"
            logger.info(f"发现视频文件: {video_url}")
            await STRM_File(video_url, name, current_path)
        else:
            logger.info(f"发现其他文件: {full_path}")

async def Get_Names_from_Folder(folder_url):
    retries = 0
    async with aiohttp.ClientSession() as session:
        while retries < max_retries:
            try:
                async with session.post(folder_url, headers=headers, data=data) as response:
                    logger.info(f"请求 URL: {folder_url}，状态码: {response.status}")
                    if response.status == 200:
                        response_data = await response.text()
                        return json.loads(response_data).get("files", [])
                    elif response.status == 500:
                        logger.error(f"服务器错误，状态码: {response.status}。重试 {retries + 1}/{max_retries} 次。")
                        retries += 1
                        await asyncio.sleep(10)
                    else:
                        logger.error(f"请求失败，状态码: {response.status}")
                        return []
            except Exception as e:
                logger.error(f"请求失败，异常信息: {e}")
                return []
        logger.error("重试次数已达上限，放弃请求。")
        return []

if __name__ == "__main__":
    result = asyncio.run(Get_List())
    if result:
        files = result.get("files", [])
        if files:
            asyncio.run(Extract_Names_and_Post(files))
        else:
            logger.debug("files 列表为空")
    else:
        logger.debug("未返回任何结果")
