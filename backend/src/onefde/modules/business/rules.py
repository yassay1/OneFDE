"""Routing order and release-scoped FAQ for the quote product."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Answer:
    id: str
    question: re.Pattern
    text: str
    revision: str = "quote-faq@1"
    product_version: str = "demo-supplier-quotes@1.1.0"


# Checked against the shipped parser, comparison rules and export buttons.
FAQ = (
    Answer(
        "csv-format",
        re.compile(r"csv.{0,8}(格式|表头|字段|列)|(?:什么|哪种|支持).{0,8}csv"),
        "请用 UTF-8 CSV。表头为 supplier,product,grade,spec,unit,unit_price,currency,note。",
    ),
    Answer(
        "pending-reason",
        re.compile(
            r"(为什么|原因|为何|什么意思).{0,12}待核对|待核对.{0,8}(原因|是什么|什么意思|为什么)"
        ),
        "必要字段缺失、单位不为 kg、报价无效或币种非 CNY 等情况会标为待核对。可查看该行的「原因」列。",
    ),
    Answer(
        "export",
        re.compile(r"(如何|怎么|怎样|哪里|能否).{0,8}导出|^导出(方式|方法)[？?。]?$"),
        "比较完成后，点击「导出全部结果 CSV」或「导出待核对 CSV」。",
    ),
)
FOUNDER = re.compile(
    r"人工|真人|转客服|创始人|多少钱|怎么收费|报价多少|(?:给|发|要|提供|需要).{0,5}报价(?!工具)"
    r"|^报价[？?。]?$|^价格[？?。]?$|服务价格|价格多少|费用|交期|(?:什么时候|多久).{0,4}(交付|上线|完成)|承诺|保证|合同"
)
FAULT = re.compile(
    r"报错|错误|故障|失败|无法|不能|不出来|打不开|没反应|不工作|卡住|崩溃|闪退|显示不对|不正确|结果不对|不准确"
)
FEATURE = re.compile(
    r"想要|希望|能不能.{0,5}(加|改)|新需求|想.{0,4}(加|改|支持)|能否.{0,5}(添加|支持)|增加|新增|改成"
)
VERSION = re.compile(r"(?<![a-z0-9])v?\d+\.\d+(?:\.\d+)?(?![a-z0-9])")


def route(text, version_hint, *, intake=None):
    text = text.casefold().strip()
    if FOUNDER.search(text):
        return "founder", None
    if intake == "support" or FAULT.search(text):
        return "support", None
    if intake == "requirement" or FEATURE.search(text):
        return "requirement", None
    versions = VERSION.findall(text)
    if version_hint:
        versions.append(version_hint.strip().casefold())
    if all(
        version in ("1.1", "1.1.0", "v1.1", "v1.1.0", "demo-supplier-quotes@1.1.0")
        for version in versions
    ):
        for answer in FAQ:
            if answer.question.search(text):
                return "faq", answer
    return "clarify", None


def concrete(text, support):
    text = text.casefold()
    if support:
        return bool(
            re.search(r"导入|上传|选择|点击|比较|导出|打开|下载|csv", text)
            and re.search(
                r"提示|显示|报错|错误码|第.{0,3}行|失败|无反应|没反应|卡住|缺少", text
            )
        )
    return bool(
        re.search(r"希望|想|需要|加|改|支持", text)
        and re.search(
            r"导入|导出|显示|筛选|比较|录入|库存|保存|扫码|统计|提醒|打印|同步", text
        )
    )
