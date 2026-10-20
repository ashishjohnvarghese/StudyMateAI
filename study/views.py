
import fitz
import re
import random
from collections import Counter
from django.shortcuts import render


def create_summary(text, sentence_limit=8):
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [
        sentence.strip()
        for sentence in sentences
        if len(sentence.split()) >= 5
    ]

    if not sentences:
        return "Not enough readable text to create a summary."

    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    word_frequency = Counter(words)

    scored_sentences = []

    for index, sentence in enumerate(sentences):
        sentence_words = re.findall(
            r"\b[a-zA-Z]{3,}\b", sentence.lower()
        )
        score = sum(word_frequency[word] for word in sentence_words)
        scored_sentences.append((index, score, sentence))

    top_sentences = sorted(
        scored_sentences,
        key=lambda item: item[1],
        reverse=True
    )[:sentence_limit]

    top_sentences.sort(key=lambda item: item[0])

    return " ".join(item[2] for item in top_sentences)


def create_quiz(text, question_limit=5):
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"\S+@\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    sentences = re.split(r"(?<=[.!?])\s+", text)

    stop_words = {
        "about", "after", "again", "against", "also", "among",
        "because", "before", "being", "between", "could", "does",
        "during", "each", "from", "have", "having", "into", "more",
        "most", "other", "over", "same", "should", "some", "such",
        "than", "that", "their", "them", "then", "there", "these",
        "they", "this", "those", "through", "under", "very", "were",
        "what", "when", "where", "which", "while", "with", "would",
        "your", "will", "been", "being", "both", "only", "using",
        "used", "many", "much", "make", "made", "like", "important",
        "however", "therefore", "often", "must", "each", "within",
        "without", "between", "include", "includes", "including"
    }

    candidates = []

    for sentence in sentences:
        sentence = sentence.strip()
        words = re.findall(r"\b[A-Za-z]+\b", sentence)

        if len(words) < 8 or len(words) > 35:
            continue

        if len(sentence) < 40:
            continue

        useful_words = [
            word for word in words
            if len(word) >= 5
            and word.lower() not in stop_words
        ]

        if useful_words:
            candidates.append((sentence, useful_words))

    if not candidates:
        return []

    random.shuffle(candidates)

    quiz = []
    used_answers = set()

    all_words = re.findall(r"\b[A-Za-z]{5,}\b", text)
    word_counts = Counter(word.lower() for word in all_words)

    word_pool = list({
        word for word in all_words
        if word.lower() not in stop_words
        and word_counts[word.lower()] >= 2
    })

    if len(word_pool) < 4:
        word_pool = list({
            word for word in all_words
            if word.lower() not in stop_words
        })

    for sentence, useful_words in candidates:
        if len(quiz) >= question_limit:
            break

        possible_answers = [
            word for word in useful_words
            if word.lower() not in used_answers
        ]

        if not possible_answers:
            continue

        answer = max(possible_answers, key=len)
        used_answers.add(answer.lower())

        question_text = re.sub(
            rf"\b{re.escape(answer)}\b",
            "________",
            sentence,
            count=1,
            flags=re.IGNORECASE
        )

        distractors = [
            word for word in word_pool
            if word.lower() != answer.lower()
            and word.lower() not in used_answers
            and abs(len(word) - len(answer)) <= 5
        ]

        if len(distractors) < 3:
            distractors = [
                word for word in word_pool
                if word.lower() != answer.lower()
                and word.lower() not in used_answers
            ]

        distractors = list({
            word.lower(): word for word in distractors
        }.values())

        random.shuffle(distractors)
        options = [answer] + distractors[:3]

        if len(options) < 4:
            continue

        random.shuffle(options)

        quiz.append({
            "question": question_text,
            "options": options,
            "answer": answer,
        })

    return quiz


def home(request):
    extracted_text = ""
    summary = ""
    error = None
    quiz = []
    quiz_results = []
    score = None
    show_extracted_text = False

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "check_quiz":
            quiz = request.session.get("quiz", [])
            extracted_text = request.session.get(
                "extracted_text", ""
            )

            if not quiz:
                error = (
                    "Please upload a PDF and generate a quiz first."
                )
            else:
                score = 0

                for index, question in enumerate(quiz):
                    selected_answer = request.POST.get(
                        f"answer_{index}", ""
                    )
                    correct_answer = question["answer"]

                    is_correct = (
                        selected_answer.strip().lower()
                        == correct_answer.strip().lower()
                    )

                    if is_correct:
                        score += 1

                    quiz_results.append({
                        "question": question["question"],
                        "selected_answer": selected_answer,
                        "correct_answer": correct_answer,
                        "is_correct": is_correct,
                    })

        else:
            uploaded_file = request.FILES.get("pdf_file")

            if not uploaded_file:
                error = "Please upload a PDF file first."

            elif not uploaded_file.name.lower().endswith(".pdf"):
                error = "Please upload a valid PDF file."

            else:
                try:
                    pdf_bytes = uploaded_file.read()

                    with fitz.open(
                        stream=pdf_bytes,
                        filetype="pdf"
                    ) as pdf:
                        extracted_text = "\n".join(
                            page.get_text() for page in pdf
                        ).strip()

                    if not extracted_text:
                        error = (
                            "No readable text was found in this PDF. "
                            "It may contain scanned pages."
                        )

                    else:
                        request.session["extracted_text"] = extracted_text

                        if action in ("extract", "extract_text"):
                            show_extracted_text = True

                        elif action == "summarize":
                            summary = create_summary(extracted_text)

                        elif action == "generate_quiz":
                            quiz = create_quiz(extracted_text)

                            if quiz:
                                request.session["quiz"] = quiz
                            else:
                                error = (
                                    "I couldn't create enough useful "
                                    "questions from this PDF. Try a PDF "
                                    "with more readable text."
                                )

                except Exception:
                    error = (
                        "There was a problem reading this PDF. "
                        "Please try another PDF file."
                    )

    context = {
        "extracted_text": extracted_text,
        "show_extracted_text": show_extracted_text,
        "summary": summary,
        "error": error,
        "quiz": quiz,
        "score": score,
        "quiz_results": quiz_results,
    }

    return render(request, "study/home.html", context)
