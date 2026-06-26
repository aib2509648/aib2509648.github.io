import streamlit as st
import google.generativeai as genai
import json
import re
from PyPDF2 import PdfReader

genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

model = genai.GenerativeModel("gemini-2.5-flash")


def format_quiz_output(text):
    text = re.sub(r"\s+([A-D])\s*[\.\)]\s*", r"\n\n\1. ", text)
    text = re.sub(r"\s+(\*\*?Đáp án đúng:?\*\*?)", r"\n\n\1", text)
    text = re.sub(r"\s+(\*\*?Giải thích:?\*\*?)", r"\n\n\1", text)
    return text.strip()


def parse_quiz(text):
    text = format_quiz_output(text)
    json_text = text.strip()

    if json_text.startswith("```"):
        json_text = re.sub(r"^```(?:json)?\s*", "", json_text)
        json_text = re.sub(r"\s*```$", "", json_text)

    try:
        data = json.loads(json_text)
        questions = []

        for item in data:
            options = item.get("options", {})
            answer = str(item.get("answer", "")).upper().strip()

            if item.get("question") and len(options) == 4 and answer in options:
                questions.append(
                    {
                        "question": item["question"],
                        "options": options,
                        "answer": answer,
                        "explanation": item.get("explanation", ""),
                    }
                )

        if questions:
            return questions
    except json.JSONDecodeError:
        pass

    blocks = re.split(r"(?m)^###\s*Câu\s+\d+\s*:\s*", text)
    questions = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = [line.strip() for line in block.splitlines() if line.strip()]
        question = lines[0].strip("# ").strip()
        options = {}
        answer = ""
        explanation = ""

        for line in lines[1:]:
            option_match = re.match(r"^([A-D])[\.\)]\s*(.+)", line)
            answer_match = re.search(r"Đáp án đúng:?\*{0,2}\s*([A-D])", line, re.IGNORECASE)
            explanation_match = re.search(r"Giải thích:?\*{0,2}\s*(.+)", line, re.IGNORECASE)

            if option_match:
                options[option_match.group(1)] = option_match.group(2).strip()
            elif answer_match:
                answer = answer_match.group(1).upper()
            elif explanation_match:
                explanation = explanation_match.group(1).strip()

        if question and len(options) == 4 and answer:
            questions.append(
                {
                    "question": question,
                    "options": options,
                    "answer": answer,
                    "explanation": explanation,
                }
            )

    return questions


st.title("Tạo Đề Trắc Nghiệm - Tran Trung Ai")

uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])
question_count = st.number_input(
    "Chọn số câu hỏi",
    min_value=1,
    max_value=50,
    value=10,
    step=1,
)

if uploaded_file:
    pdf = PdfReader(uploaded_file)

    text = ""

    for page in pdf.pages:
        text += page.extract_text()

    st.success("Đã đọc PDF!")

    if st.button("Tạo câu hỏi"):
        prompt = f"""
        Dựa vào nội dung sau:
        {text}
        Hãy tạo {question_count} câu hỏi trắc nghiệm.
        Chỉ trả về JSON hợp lệ, không viết thêm chữ bên ngoài.
        JSON phải là một mảng, mỗi phần tử có dạng:
        {{
          "question": "Nội dung câu hỏi",
          "options": {{
            "A": "Đáp án A",
            "B": "Đáp án B",
            "C": "Đáp án C",
            "D": "Đáp án D"
          }},
          "answer": "A",
          "explanation": "Giải thích ngắn"
        }}
        """

        with st.spinner("Đang tạo câu hỏi..."):
            response = model.generate_content(prompt)

        st.session_state.quiz_questions = parse_quiz(response.text)
        st.session_state.quiz_submitted = False

    def reset_score():
        st.session_state.quiz_submitted = False

    if "quiz_questions" in st.session_state and st.session_state.quiz_questions:
        if "quiz_submitted" not in st.session_state:
            st.session_state.quiz_submitted = False

        for index, item in enumerate(st.session_state.quiz_questions, start=1):
            st.subheader(f"Câu {index}: {item['question']}")

            choices = [
                f"{key}. {value}"
                for key, value in item["options"].items()
            ]

            selected = st.radio(
                "Chọn đáp án",
                choices,
                index=None,
                key=f"question_{index}",
                on_change=reset_score,
            )

            if st.session_state.quiz_submitted and selected:
                selected_key = selected.split(".", 1)[0]

                if selected_key == item["answer"]:
                    st.success(f"Đúng rồi! Đáp án đúng là {item['answer']}.")
                else:
                    correct_text = item["options"][item["answer"]]
                    st.error(
                        f"Chưa đúng. Đáp án đúng là {item['answer']}. {correct_text}"
                    )

                if item["explanation"]:
                    st.info(item["explanation"])

            st.divider()

        if st.button("Chấm Điểm"):
            st.session_state.quiz_submitted = True
            st.rerun()

        if st.session_state.quiz_submitted:
            total_questions = len(st.session_state.quiz_questions)
            correct_count = 0
            unanswered_count = 0

            for index, item in enumerate(st.session_state.quiz_questions, start=1):
                selected = st.session_state.get(f"question_{index}")

                if not selected:
                    unanswered_count += 1
                    continue

                selected_key = selected.split(".", 1)[0]

                if selected_key == item["answer"]:
                    correct_count += 1

            wrong_count = total_questions - correct_count - unanswered_count
            score = correct_count / total_questions * 10

            st.subheader("Kết Quả")
            st.metric("Điểm", f"{score:.1f}/10")
            st.write(
                f"Đúng: {correct_count}/{total_questions} | "
                f"Sai: {wrong_count} | "
                f"Không Trả Lời: {unanswered_count}"
            )
    elif "quiz_questions" in st.session_state:
        st.warning("Chưa tách được quiz tự động. Bấm Tạo câu hỏi lại giúp mình nhé.")