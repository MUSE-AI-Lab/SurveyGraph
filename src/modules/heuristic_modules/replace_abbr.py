import re


class AbbrReplacer(object):
    def __init__(self):
        self._abbr_dict = {}  # 用于存储全称和缩写对
        self.first_occurrences = set()  # 记录首次出现需要例外处理的全称
        # 使用正则表达式匹配全称和缩写
        # 增加逻辑确保缩写字母数和全称中的单词数一致
        self.pattern = re.compile(r"\s+\(([A-Z]+)\)")
        self.punc_pattern = re.compile(r"[,.]\s*|\n")

    def find_abbr_pairs(self, content: str):
        segs = re.split(self.punc_pattern, content)
        for one in segs:
            one = one.strip()
            if one == "":
                continue
            matches = re.finditer(self.pattern, one)
            for match in matches:
                abbr = match.group(1)
                pos = match.start()  # 缩写的起始位置

                # abbr 需要为一个单词
                if len(abbr.strip().split()) > 1:
                    continue
                words_num = len(abbr)

                # 统计全称的单词数
                words = one[:pos].strip().split()[-words_num:]

                full_name = " ".join(words)

                # 进一步检查缩写是否匹配这些单词的首字母
                if all(
                    word[0].upper() == abbr_char for word, abbr_char in zip(words, abbr)
                ):
                    if full_name not in self._abbr_dict:
                        self._abbr_dict[full_name] = abbr
                        self.first_occurrences.add(full_name)  # 添加到首次出现的集合
        return self._abbr_dict

    # 替换全称为缩写 (首次出现的情况例外)
    def replace_full_name_with_abbr(self, match):
        # 只取全称部分进行匹配
        full_name_only = match.group(1)
        if full_name_only in self.first_occurrences:
            # 是首次出现，移除后跳过替换
            self.first_occurrences.remove(full_name_only)
            return match.group(0)  # 返回未修改的整个匹配内容
        # 使用缩写替换
        return self._abbr_dict[full_name_only]

    def process(self, content: str):
        # 先收集新的缩写对
        self.find_abbr_pairs(content)

        # 文本处理：替换掉全称和全称(缩写)
        for full_name, abbr in self._abbr_dict.items():
            full_name_pattern = (
                r"\b(" + re.escape(full_name) + r")(\s+\(" + re.escape(abbr) + r"\))?"
            )
            content = re.sub(
                full_name_pattern, self.replace_full_name_with_abbr, content
            )

        return content


# 示例使用
if __name__ == "__main__":
    replacer = AbbrReplacer()
    text = """Natural Language Processing (NLP) is a branch of artificial intelligence (AI).
              This course on Natural Language Processing (NLP) will cover several topics in artificial intelligence .
              Natural Language Processing  is a branch of artificial intelligence .
              This course on Natural Language Processing (NLP) will cover several topics in artificial intelligence ."""
    processed_text = replacer.process(text)
    print(processed_text)
