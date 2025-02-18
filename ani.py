import asyncio, aiohttp, sys, aiofiles, json, os
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import xml.dom.minidom
from datetime import datetime
from loguru import logger

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss:SSS}</green> | <level>{level: <8}</level> | <green>{name}:{function}:{line}</green> - <level>{message}</level>",
    level="DEBUG"
)
xmlurl = "https://api.ani.rip/ani-download.xml"
ani = "https://ani.0m.ee/"
headers = {
    'origin': ani,
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    "Content-Type": "application/json"
}
data = '{"password":"null"}'
cron = '*/2 * * * *'  # cron执行周期
max_retries = 5
strm_directory = '/root/strm'  # strm文件保存路径
os.makedirs(strm_directory, exist_ok=True)

def Current_Quarter():
    return f'{datetime.now().year}-{[m for m in [10, 7, 4, 1] if m <= datetime.now().month][0]}'

async def Fetch_Xml(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()

def Get_Latest_List(dom):
    return [{'title': t.firstChild.nodeValue} for t in dom.getElementsByTagName('title') if t.firstChild]

async def STRM_File(video_url, name, folder, strm):
    filename = os.path.join(strm_directory, folder, f"{os.path.splitext(name)[0]}.strm")
    os.makedirs(os.path.join(strm_directory, folder), exist_ok=True)
    if os.path.exists(filename):
        async with aiofiles.open(filename, 'r', encoding='utf-8') as f:
            existing_content = await f.read()
            if existing_content.strip() == f"{video_url}?d=true":
                return strm
    async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
        await f.write(f"{video_url}?d=true")
    logger.info(f"成功创建 strm 文件: {filename}")
    return strm + 1

async def Parse_Xml(xml_data, strm=0):
    dom = xml.dom.minidom.parseString(xml_data)
    rss_list = Get_Latest_List(dom)
    quarter = Current_Quarter()
    logger.info(f'本次处理 {len(rss_list)} 个文件')
    for rss in rss_list:
        strm = await STRM_File(f"{ani}/{quarter}/{rss['title']}", rss['title'], quarter, strm)
    return strm

async def _Task():
    xml_data = await Fetch_Xml(xmlurl)
    strm = await Parse_Xml(xml_data)
    logger.info(f"成功处理 {strm} 个文件")

def Run_Task():
    asyncio.run(_Task())

async def Get_List():
    retries = 0
    async with aiohttp.ClientSession() as session:
        while retries < max_retries:
            try:
                async with session.post(ani, headers=headers, data=data) as response:
                    if response.status == 200:
                        return json.loads(await response.text())
                    logger.error(f"请求错误，状态码: {response.status}。重试 {retries + 1}")
                    retries += 1
                    await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"请求异常: {e}")
        return None

async def Extract_Names_and_Post(files, path="", strm=0):
    for file in files:
        name = file["name"]
        mime_type = file["mimeType"]
        full_path = os.path.join(path, name)
        if "folder" in mime_type:
            os.makedirs(os.path.join(strm_directory, full_path), exist_ok=True)
            folder_files = await Get_Names_from_Folder(f"{ani}{full_path}/")
            strm = await Extract_Names_and_Post(folder_files, full_path, strm)
        elif "video" in mime_type:
            video_url = f"{ani}{full_path}"
            strm = await STRM_File(video_url, name, path, strm)
    return strm

async def Get_Names_from_Folder(folder_url):
    retries = 0
    async with aiohttp.ClientSession() as session:
        while retries < max_retries:
            try:
                async with session.post(folder_url, headers=headers, data=data) as response:
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
        logger.error("重试次数已达上限")
        return []

if __name__ == "__main__":
    mode = input("请输入模式：(1)所有番剧/(2)追新番\n")
    if mode == "1":
        result = asyncio.run(Get_List())
        if result and result.get("files"):
            strm = asyncio.run(Extract_Names_and_Post(result["files"]))
            logger.info(f"成功处理 {strm} 个文件")
    elif mode == "2":
        logger.info(f"执行周期: {cron}")
        scheduler = BlockingScheduler()
        scheduler.add_job(Run_Task, trigger=CronTrigger.from_crontab(cron))
        scheduler.start()
    else:
        print("无效输入，请输入1或2")
