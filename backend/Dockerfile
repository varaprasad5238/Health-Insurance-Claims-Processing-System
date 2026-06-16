FROM public.ecr.aws/lambda/python:3.13

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/var/task \
    CLAIMS_STORAGE_ROOT=/tmp/claims

WORKDIR /var/task

COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r ./backend/requirements.txt

COPY backend ./backend
COPY assignment ./assignment
COPY test_suite ./test_suite

CMD ["backend.main.handler"]
