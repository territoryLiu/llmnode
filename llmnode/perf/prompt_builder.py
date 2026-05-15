from __future__ import annotations


def count_prompt_tokens(tokenizer, prompt: str) -> int:
    token_ids = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=True,
        add_generation_prompt=True,
    )
    return len(token_ids)


def build_prompt_for_target(
    tokenizer,
    target_prompt_tokens: int,
    base_fragment: str = "hello ",
) -> tuple[str, int]:
    lo, hi = 1, max(1, target_prompt_tokens)
    best_prompt = ""
    best_count = 0

    while lo <= hi:
        mid = (lo + hi) // 2
        prompt = " ".join([base_fragment] * mid)
        token_count = count_prompt_tokens(tokenizer, prompt)
        if token_count <= target_prompt_tokens:
            best_prompt = prompt
            best_count = token_count
            lo = mid + 1
        else:
            hi = mid - 1

    return best_prompt, best_count
