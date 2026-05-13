"""common.swagger.add_field_examples hook 단위 테스트."""

from common.swagger import add_field_examples


def _run(schemas: dict) -> dict:
    result = {"components": {"schemas": schemas}}
    return add_field_examples(result, generator=None, request=None, public=True)


class TestAddFieldExamples:
    def test_글로벌_필드는_매핑된_example_을_받는다(self):
        result = _run({"Anything": {"properties": {"uid": {"type": "string"}}}})

        assert result["components"]["schemas"]["Anything"]["properties"]["uid"]["example"] == (
            "8f3e2b1a-1234-4abc-9def-1234567890ab"
        )

    def test_컴포넌트별_override_가_우선(self):
        schemas = {
            "HomeCreateRequest": {"properties": {"name": {"type": "string"}}},
            "UserProfileOutput": {"properties": {"name": {"type": "string"}}},
        }

        result = _run(schemas)

        assert result["components"]["schemas"]["HomeCreateRequest"]["properties"]["name"]["example"] == "우리집"
        assert result["components"]["schemas"]["UserProfileOutput"]["properties"]["name"]["example"] == "홍길동"

    def test_이미_example_이_있으면_덮어쓰지_않는다(self):
        schemas = {"X": {"properties": {"uid": {"type": "string", "example": "fixed"}}}}

        result = _run(schemas)

        assert result["components"]["schemas"]["X"]["properties"]["uid"]["example"] == "fixed"

    def test_매핑_없는_필드는_예시가_부여되지_않는다(self):
        schemas = {"X": {"properties": {"some_random_field": {"type": "string"}}}}

        result = _run(schemas)

        assert "example" not in result["components"]["schemas"]["X"]["properties"]["some_random_field"]

    def test_매핑되지_않은_컴포넌트는_글로벌_fallback(self):
        # HomeMember 는 컴포넌트별에 name=홍길동 정의돼 있지만, 매핑되지 않은 컴포넌트(예: ForeignComponent)는
        # 글로벌만 적용된다.
        schemas = {"ForeignComponent": {"properties": {"name": {"type": "string"}, "uid": {"type": "string"}}}}

        result = _run(schemas)

        props = result["components"]["schemas"]["ForeignComponent"]["properties"]
        assert "example" not in props["name"]  # 글로벌에 name 없음
        assert props["uid"]["example"] == "8f3e2b1a-1234-4abc-9def-1234567890ab"
