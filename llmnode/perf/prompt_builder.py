from __future__ import annotations


def _count_tokenized_output(tokenized) -> int:
    if hasattr(tokenized, "encodings") and tokenized.encodings:
        first_encoding = tokenized.encodings[0]
        if hasattr(first_encoding, "ids"):
            return len(first_encoding.ids)
    if hasattr(tokenized, "input_ids"):
        input_ids = tokenized.input_ids
        if input_ids and isinstance(input_ids[0], list):
            return len(input_ids[0])
        return len(input_ids)
    return len(tokenized)


def count_prompt_tokens(tokenizer, prompt: str) -> int:
    token_ids = tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=True,
        add_generation_prompt=True,
    )
    return _count_tokenized_output(token_ids)



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
