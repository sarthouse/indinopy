import io
from abc import ABC, abstractmethod
from typing import Any, Optional
from django.http import HttpResponse
from django.template.loader import render_to_string


class BaseReport(ABC):
    nombre_archivo: str = "reporte"
    content_type: str = "text/plain"
    extension: str = "txt"

    def __init__(self, objeto_origen: Any = None, request: Optional[Any] = None, **kwargs):
        self.objeto = objeto_origen
        self.request = request
        self.params = kwargs

    @abstractmethod
    def render(self) -> bytes:
        pass

    def get_filename(self) -> str:
        base = self.nombre_archivo.rstrip(f".{self.extension}")
        return f"{base}.{self.extension}"

    def to_http_response(self, inline: bool = False) -> HttpResponse:
        contenido = self.render()
        response = HttpResponse(contenido, content_type=self.content_type)
        disposition = "inline" if inline else "attachment"
        filename = self.get_filename()
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response


class BasePDFReport(BaseReport):
    template_name: str
    content_type: str = "application/pdf"
    extension: str = "pdf"

    def get_context_data(self) -> dict:
        return {"objeto": self.objeto, "params": self.params}

    def render(self) -> bytes:
        context = self.get_context_data()
        html_string = render_to_string(self.template_name, context)
        try:
            from weasyprint import HTML
            return HTML(string=html_string).write_pdf()
        except ImportError:
            # Fallback en caso de que Weasyprint no esté instalado en el entorno de desarrollo
            return html_string.encode("utf-8")
