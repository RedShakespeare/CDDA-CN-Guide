# -*- coding: UTF-8 -*-

from prettytable import PrettyTable
import re
import os
import time
import aiohttp
import asyncio
from urllib import parse
from PyInquirer import prompt, Separator
from examples import custom_style_2
from colr import color
from cfonts import render, say


class ExportMD:
    def __init__(self):
        self.repo_table = PrettyTable(["知识库ID", "名称"])
        self.namespace, self.Token = self.get_UserInfo()
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "ExportMD",
            "X-Auth-Token": self.Token
        }
        self.repo = {}
        self.export_dir = './'

    def print_logo(self):
        output = render('ExportMD', colors=['red', 'yellow'], align='center')
        print(output)

    # 语雀用户信息
    def get_UserInfo(self):
        f_name = ".userinfo"
        if os.path.isfile(f_name):
            with open(f_name, encoding="utf-8") as f:
                userinfo = f.read().split("&")
        else:
            namespace = 'silencess'
            Token = os.environ['YUQUE_TOKEN']
            userinfo = [namespace, Token]
            with open(f_name, "w") as f:
                f.write(namespace + "&" + Token)
        return userinfo

    # 发送请求
    async def req(self, session, api):
        url = "https://www.yuque.com/api/v2" + api
        # print(url)
        async with session.get(url, headers=self.headers) as resp:
            result = await resp.json()
            return result

    # 获取所有知识库
    async def getRepo(self):
        api = "/users/%s/repos" % self.namespace
        async with aiohttp.ClientSession() as session:
            result = await self.req(session, api)
            for repo in result.get('data'):
                repo_id = str(repo['id'])
                repo_name = repo['name']
                self.repo[repo_name] = repo_id
                self.repo_table.add_row([repo_id, repo_name])

    # 获取一个知识库的文档列表
    async def get_docs(self, repo_id):
        api = "/repos/%s/docs" % repo_id
        async with aiohttp.ClientSession() as session:
            result = await self.req(session, api)
            docs = {}
            for doc in result.get('data'):
                title = doc['title']
                slug = doc['slug']
                docs[slug] = title
            return docs

    # 获取正文 Markdown 源代码
    async def get_body(self, repo_id, slug):
        api = "/repos/%s/docs/%s" % (repo_id, slug)
        async with aiohttp.ClientSession() as session:
            result = await self.req(session, api)
            body = result['data']['body']
            body = re.sub("<a name=\".*\"></a>","", body)  # 正则去除语雀导出的<a>标签
            body = re.sub("\x00", "", body) # 去除不可见字符\x00
            body = re.sub("\x05", "", body) # 去除不可见字符\x05
            body = re.sub(r'\<br \/\>!\[image.png\]',"\n![image.png]",body) # 正则去除语雀导出的图片后紧跟的<br \>标签
            body = re.sub(r'\)\<br \/\>', ")\n", body)  # 正则去除语雀导出的图片后紧跟的<br \>标签
            return body

    # 选择知识库
    def selectRepo(self):
        return ['CataclysmDDA综合攻略手册']

    # 创建文件夹
    def mkDir(self, dir):
        isExists = os.path.exists(dir)
        if not isExists:
            os.makedirs(dir)

    # 获取文章并执行保存
    async def download_md(self, repo_id, slug, repo_name, title):
        """
        :param repo_id: 知识库id
        :param slug: 文章id
        :param repo_name: 知识库名称
        :param title: 文章名称
        :return: none
        """
        body = await self.get_body(repo_id, slug)
        new_body, image_list = await self.to_local_image_src(body)

        if image_list:
            # 图片保存位置: ./<repo_name>/docs/media/<filename>
            save_dir = os.path.join(self.export_dir, repo_name, "docs", "media")
            self.mkDir(save_dir)
            async with aiohttp.ClientSession() as session:
                await asyncio.gather(
                    *(self.download_image(session, image_info, save_dir) for image_info in image_list)
                )

        self.save(repo_name, title, new_body)

        print("📑 %s 导出成功！" % color(title, fore='green', style='bright'))

    # 将md里的图片地址替换成本地的图片地址
    async def to_local_image_src(self, body):
        body = re.sub(r'\<br \/\>!\[image.png\]',"\n![image.png]",body) # 正则去除语雀导出的图片后紧跟的<br \>标签
        body = re.sub(r'\)\<br \/\>', ")\n", body)  # 正则去除语雀导出的图片后紧跟的<br \>标签
        
        pattern = r"!\[(?P<img_name>.*?)\]" \
                  r"\((?P<img_src>https:\/\/cdn\.nlark\.com\/yuque.*\/(?P<slug>\d+)\/(?P<filename>.*?\.[a-zA-z]+)).*\)"
        repl = r"![\g<img_name>](./media/\g<filename>)"
        images = [_.groupdict() for _ in re.finditer(pattern, body)]
        new_body = re.sub(pattern, repl, body)
        return new_body, images

    # 下载图片
    async def download_image(self, session, image_info: dict, save_dir: str):
        img_src = image_info['img_src']
        filename = image_info["filename"]

        async with session.get(img_src) as resp:
            with open(os.path.join(save_dir, filename), 'wb') as f:
                f.write(await resp.read())

    # 保存文章
    def save(self, repo_name, title, body):
        # 将不能作为文件名的字符进行编码
        def check_safe_path(path: str):
            for char in r'/\<>?:"|*':
                path = path.replace(char, parse.quote_plus(char))
            return path

        repo_name = check_safe_path(repo_name)
        title = check_safe_path(title)
        save_path = "./%s/docs/%s.md" % (repo_name, title)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(body)

    async def run(self):
        self.print_logo()
        await self.getRepo()
        repo_name_list = self.selectRepo()
        
        self.mkDir(self.export_dir)  # 创建用于存储知识库文章的文件夹

        # 遍历所选知识库
        for repo_name in repo_name_list:
            dir_path = self.export_dir + "/" + repo_name.replace("/", "%2F") + "/" + "docs"
            dir_path.replace("//", "/")
            self.mkDir(dir_path)

            repo_id = self.repo[repo_name]
            docs = await self.get_docs(repo_id)
            
            # 异步导出接口会报错，修改为同步导出，且每次导出等待50ms
            for slug in docs:
                time.sleep(0.05)
                title = docs[slug]
                await self.download_md(repo_id, slug, repo_name, title)

#             await asyncio.gather(
#                 *(self.download_md(repo_id, slug, repo_name, title) for slug, title in docs.items())
#             )

        print("\n" + color('🎉 导出完成！', fore='green', style='bright'))
        print("已导出到：" + color(os.path.realpath(self.export_dir), fore='green', style='bright'))


if __name__ == '__main__':
    export = ExportMD()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(export.run())
