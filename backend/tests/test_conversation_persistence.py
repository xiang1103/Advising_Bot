'''
Integration tests for the chat persistence path.

This is the seam that /chat depends on and that no amount of mocking can
verify: create_thread_table_entry -> save_conversation -> get_history, running
against a real Postgres with the real schema, the real foreign key, and the
real PostgREST layer in between.

Every test here asserts a property that backend/routers/chat.py already relies
on today, so a failure means the endpoint is broken, not that a test is fussy.

Run with:
    supabase start && supabase db reset
    pytest backend/tests/test_conversation_persistence.py
'''

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration

BASE_TIME = datetime(2026, 8, 25, 15, 0, tzinfo=timezone.utc)

# Comfortably larger than any thread these tests build, so one page holds it all.
WHOLE_THREAD = 100


def record_turn(ops, thread_id, question, answer, offset_seconds):
    '''
    Save one user/bot exchange the way routers.chat.persist_conversation does:
    the question is timestamped when it arrives, the answer once the stream ends.
    '''
    asked_at = BASE_TIME + timedelta(seconds=offset_seconds)
    answered_at = asked_at + timedelta(seconds=2)
    ops.save_conversation(
        thread_id=thread_id,
        user_msg=question,
        bot_response=answer,
        ask_time=asked_at,
        answer_time=answered_at,
    )


def chronological(ops, thread_id):
    '''
    The whole thread oldest-first.

    get_history returns newest-first for the UI; reversing one full page is the
    readable way to assert on conversation order.
    '''
    newest_first = ops.get_history(thread_id, page_num=1, page_size=WHOLE_THREAD)
    return list(reversed(newest_first))


def test_thread_and_conversation_round_trip(ops):
    '''
    The core contract: a thread plus one exchange goes in, and comes back out
    as [user, advising_bot] with content intact.
    '''
    thread_id = str(uuid4())

    ops.create_thread_table_entry(thread_id, "CSE major requirements")
    record_turn(
        ops,
        thread_id,
        question="What are the prerequisites for CSE 214?",
        answer="CSE 214 requires CSE 114 with a grade of C or higher.",
        offset_seconds=0,
    )

    history = chronological(ops, thread_id)

    assert [row["role"] for row in history] == ["user", "advising_bot"]
    assert history[0]["content"] == "What are the prerequisites for CSE 214?"
    assert history[1]["content"] == "CSE 214 requires CSE 114 with a grade of C or higher."


def test_create_thread_table_entry_is_idempotent(ops, db):
    '''
    /chat calls create_thread_table_entry on *every* message, not just the
    first, so re-running it must neither error nor clobber the stored title.
    '''
    thread_id = str(uuid4())

    ops.create_thread_table_entry(thread_id, "Advising questions")
    ops.create_thread_table_entry(thread_id, "Renamed by a later request")

    with db.cursor() as cur:
        cur.execute("select id, title from public.threads")
        rows = cur.fetchall()

    assert len(rows) == 1, "a repeated call must not create a second thread row"
    assert rows[0][1] == "Advising questions", (
        "upsert uses ignore_duplicates=True, so the original title stands"
    )


def test_save_conversation_rejects_unknown_thread(ops):
    '''
    conversations.thread_id is a foreign key. Persisting before the thread row
    exists must fail loudly rather than silently dropping the exchange -- this
    is what pins the ordering of the two calls inside /chat.
    '''
    orphan_thread_id = str(uuid4())

    with pytest.raises(RuntimeError) as excinfo:
        record_turn(ops, orphan_thread_id, "hello?", "hi there", offset_seconds=0)

    assert orphan_thread_id in str(excinfo.value)


def test_history_preserves_turn_order_across_many_turns(ops):
    '''
    Memory correctness depends on replaying turns in the order they happened,
    strictly alternating user then bot.
    '''
    thread_id = str(uuid4())
    ops.create_thread_table_entry(thread_id, "Multi-turn thread")

    exchanges = [
        ("What is the CSE core?", "The CSE core is CSE 114, 214, 215 and 216."),
        ("Which of those is hardest?", "Students most often cite CSE 216."),
        ("When is CSE 216 offered?", "CSE 216 runs in both fall and spring."),
    ]
    for index, (question, answer) in enumerate(exchanges):
        record_turn(ops, thread_id, question, answer, offset_seconds=index * 60)

    history = chronological(ops, thread_id)

    assert [row["role"] for row in history] == ["user", "advising_bot"] * 3
    assert [row["content"] for row in history] == [
        text for exchange in exchanges for text in exchange
    ]


def test_history_is_scoped_to_its_thread(ops):
    '''
    Two conversations must not bleed into each other -- the bot would answer
    with another student's context.
    '''
    mine, theirs = str(uuid4()), str(uuid4())
    ops.create_thread_table_entry(mine, "My thread")
    ops.create_thread_table_entry(theirs, "Someone else's thread")

    record_turn(ops, mine, "my question", "my answer", offset_seconds=0)
    record_turn(ops, theirs, "their question", "their answer", offset_seconds=30)

    contents = [row["content"] for row in chronological(ops, mine)]

    assert contents == ["my question", "my answer"]


def test_get_history_paginates_without_gaps_or_duplicates(ops):
    '''
    Paging must partition the thread exactly: every message appears once, in
    newest-first order, with no row straddling or falling between pages.
    '''
    thread_id = str(uuid4())
    ops.create_thread_table_entry(thread_id, "Paged thread")

    for index in range(3):  # 3 exchanges -> 6 rows
        record_turn(
            ops,
            thread_id,
            question=f"question {index}",
            answer=f"answer {index}",
            offset_seconds=index * 60,
        )

    first_page = ops.get_history(thread_id, page_num=1, page_size=4)
    second_page = ops.get_history(thread_id, page_num=2, page_size=4)
    past_the_end = ops.get_history(thread_id, page_num=3, page_size=4)

    assert len(first_page) == 4
    assert len(second_page) == 2
    assert past_the_end == []

    paged = [row["content"] for row in first_page + second_page]
    newest_first = [row["content"] for row in reversed(chronological(ops, thread_id))]
    assert paged == newest_first


def test_list_all_threads_is_newest_first_and_respects_limit(ops, db):
    '''
    The sidebar's thread list. updated_at is set explicitly here because the
    column has no touch trigger -- the ordering under test is the query's, not
    the clock's.
    '''
    older, newer = str(uuid4()), str(uuid4())
    ops.create_thread_table_entry(older, "Older thread")
    ops.create_thread_table_entry(newer, "Newer thread")

    with db.cursor() as cur:
        cur.execute(
            "update public.threads set updated_at = %s where id = %s",
            (BASE_TIME, older),
        )
        cur.execute(
            "update public.threads set updated_at = %s where id = %s",
            (BASE_TIME + timedelta(hours=1), newer),
        )

    threads = ops.list_all_threads()

    assert [row["title"] for row in threads] == ["Newer thread", "Older thread"]
    assert [row["id"] for row in threads] == [newer, older]
    assert [row["id"] for row in ops.list_all_threads(limit=1)] == [newer]


def test_deleting_a_thread_removes_its_conversations(ops, db):
    '''
    The schema promises ON DELETE CASCADE. If that ever regresses, deleting a
    thread would strand its messages as unreachable rows.
    '''
    thread_id = str(uuid4())
    ops.create_thread_table_entry(thread_id, "Doomed thread")
    record_turn(ops, thread_id, "still here?", "not for long", offset_seconds=0)

    with db.cursor() as cur:
        cur.execute("delete from public.threads where id = %s", (thread_id,))
        cur.execute("select count(*) from public.conversations")
        remaining = cur.fetchone()[0]

    assert remaining == 0
