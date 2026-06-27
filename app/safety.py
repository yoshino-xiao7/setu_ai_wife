MINOR_TERMS = {
    "未成年",
    "小学生",
    "中学生",
    "初中生",
    "高中生",
    "幼女",
    "萝莉",
    "loli",
    "child",
    "kid",
    "teen",
    "underage",
}

SEXUAL_TERMS = {
    "裸体",
    "裸露",
    "色情",
    "性爱",
    "露点",
    "乳头",
    "下体",
    "nsfw",
    "nude",
    "naked",
    "sex",
    "explicit",
    "porn",
}


class SafetyError(ValueError):
    pass


def validate_prompt(prompt: str) -> None:
    normalized = prompt.lower().replace(" ", "")
    has_minor = any(term in normalized for term in MINOR_TERMS)
    has_sexual = any(term in normalized for term in SEXUAL_TERMS)
    if has_minor and has_sexual:
        raise SafetyError("请求同时包含疑似未成年和露骨性内容，已拒绝生成。")

