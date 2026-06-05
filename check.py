import os, sys
from dotenv import load_dotenv


CHECK_PROMPT = 'reply with the single word: OK'
REASONING_PREFIXES = ('gpt-5', 'o1', 'o3', 'o4')


def is_reasoning_model(model):
    return (model or '').startswith(REASONING_PREFIXES)


def build_response_kwargs(model):
    kwargs = {
        'model': model,
        'input': CHECK_PROMPT,
        'max_output_tokens': 128,
    }
    if is_reasoning_model(model):
        kwargs['reasoning'] = {'effort': 'minimal'}
    return kwargs


def validate_reply(reply):
    clean = (reply or '').strip()
    if not clean:
        raise ValueError('OpenAI returned an empty reply.')
    return clean


def main():
    load_dotenv()
    key = os.getenv('OPENAI_API_KEY')

    if not key or key.startswith('sk-your-key'):
        print('[FAIL] OPENAI_API_KEY is not set.')
        print('       -> Copy .env.example to .env and paste your key into it.')
        sys.exit(1)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        r = client.responses.create(**build_response_kwargs(model))
        reply = validate_reply(r.output_text)
        print('[OK] Environment ready. model=' + model + '  reply=' + reply)
    except Exception as e:
        print('[FAIL] OpenAI call failed: ' + repr(e))
        print('       -> Check your key, billing, and internet connection.')
        sys.exit(1)


if __name__ == "__main__":
    main()
