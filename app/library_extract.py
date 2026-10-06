"""Bounded local extraction: never execute macros, formulas or remote resources."""
import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from defusedxml import ElementTree as ET
from fastapi import HTTPException
from . import documents

SUPPORTED={'.pdf':'document','.docx':'document','.xlsx':'spreadsheet','.pptx':'presentation','.ods':'spreadsheet','.odt':'document','.odp':'presentation','.md':'notes','.markdown':'notes','.txt':'text','.csv':'spreadsheet','.tsv':'spreadsheet','.json':'structured','.html':'document','.htm':'document','.xml':'structured'}


def extract(name,raw):
    ext=Path(name).suffix.casefold()
    if ext not in SUPPORTED:
        raise HTTPException(422,'Unsupported format. Export Google Docs/Sheets/Slides as DOCX/XLSX/PPTX or PDF; convert legacy DOC/XLS/PPT locally.')
    if not raw or len(raw)>documents.MAX_BYTES: raise HTTPException(422,'File must contain 1–8 MB')
    chunks=[]; warnings=[]; total=0
    def add(text,locator):
        nonlocal total
        text=text.replace('\x00','').strip()
        if not text:return
        total+=len(text)
        if total>documents.MAX_CHARS: raise HTTPException(422,'Too much extracted text; split the document')
        for start in range(0,len(text),800):
            chunks.append({'text':text[start:start+1000],'locator':locator})
            if len(chunks)>300: raise HTTPException(422,'Document exceeds 300 passages; split it')
    try:
        if ext in {'.docx','.xlsx','.pptx','.ods','.odt','.odp'}:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if len(archive.infolist())>3000 or sum(i.file_size for i in archive.infolist())>32*1024*1024:
                    raise HTTPException(422,'Expanded archive exceeds limits')
                if any(i.filename.casefold().endswith('vbaproject.bin') for i in archive.infolist()):
                    raise HTTPException(422,'Macro-bearing files are not supported')
        if ext=='.pdf':
            _,pages,sections,_=documents.extract(name,raw)
            for section in sections:add(section['text'],f"page {section['page']}")
            missing=[p for p in range(1,pages+1) if p not in {s['page'] for s in sections}]
            for number in missing[:20]:
                if not shutil.which('tesseract'):
                    warnings.append(f'page {number}: local OCR unavailable');continue
                output=subprocess.run(['tesseract','stdin','stdout','-l','eng+ind'],input=documents.page_jpeg(raw,number),capture_output=True,timeout=15,check=True)
                add(output.stdout.decode('utf-8',errors='replace'),f'page {number} (OCR)')
                warnings.append(f'page {number}: OCR may contain errors')
            warnings.extend(f'page {n}: OCR page limit reached' for n in missing[20:])
        elif ext=='.xlsx':
            from openpyxl import load_workbook
            book=load_workbook(io.BytesIO(raw),read_only=True,data_only=False,keep_links=False)
            cells=0
            try:
                for sheet in book:
                    buffer=[]; first=None; last=None
                    for row in sheet.iter_rows():
                        cells+=len(row)
                        if cells>20000:raise HTTPException(422,'Spreadsheet exceeds 20,000 cells; split it')
                        values=[f'{c.coordinate}: {c.value}' for c in row if c.value is not None]
                        if values:
                            first=first or row[0].row;last=row[0].row;buffer.append(' | '.join(values))
                            if sum(len(v) for v in buffer)>=800:
                                add('\n'.join(buffer),f'sheet {sheet.title}, rows {first}-{last}');buffer=[];first=None
                    if buffer:add('\n'.join(buffer),f'sheet {sheet.title}, rows {first}-{last}')
            finally:book.close()
            warnings.append('Formulas are text, not recalculated. Charts and images are not interpreted.')
        elif ext=='.pptx':
            from pptx import Presentation
            for n,slide in enumerate(Presentation(io.BytesIO(raw)).slides,1):
                texts=[]
                for shape in slide.shapes:
                    if shape.has_text_frame:texts.append(shape.text)
                    if shape.has_table:texts.extend(' | '.join(c.text for c in row.cells) for row in shape.table.rows)
                if slide.has_notes_slide:texts.append(slide.notes_slide.notes_text_frame.text)
                add('\n'.join(texts),f'slide {n}')
            warnings.append('Slide text/tables/notes extracted; artwork/layout not visually interpreted.')
        elif ext=='.docx':
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                root=ET.fromstring(archive.read('word/document.xml'))
                paragraphs=[''.join(p.itertext()) for p in root.findall('.//w:p',{'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'})]
                add('\n'.join(paragraphs),'document text (page numbers unavailable)')
        elif ext in {'.ods','.odt','.odp'}:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                root=ET.fromstring(archive.read('content.xml'))
                add('\n'.join(' '.join(e.itertext()) for e in root.iter() if e.tag.endswith('}p')),'OpenDocument text')
            warnings.append('Complex tables/layout may require a PDF export.')
        else:
            text=raw.decode('utf-8-sig')
            if ext=='.json':json.loads(text)
            if ext=='.xml':ET.fromstring(raw)
            if ext in {'.html','.htm'}:
                from html.parser import HTMLParser
                class Parser(HTMLParser):
                    def __init__(self):super().__init__();self.parts=[];self.ignore=0
                    def handle_starttag(self,tag,attrs):
                        if tag in {'script','style'}:self.ignore+=1
                    def handle_endtag(self,tag):
                        if tag in {'script','style'}:self.ignore=max(0,self.ignore-1)
                    def handle_data(self,data):
                        if not self.ignore:self.parts.append(data)
                parser=Parser();parser.feed(text);text='\n'.join(parser.parts)
            for n,start in enumerate(range(0,len(text),4000),1):add(text[start:start+4000],f'text block {n}')
        if not chunks:raise HTTPException(422,'No readable text; convert locally or use local OCR')
        words=set(re.findall(r'\w+',' '.join(c['text'] for c in chunks[:5]).casefold()))
        topic='technical' if words&{'api','code','software','server','android'} else 'financial' if words&{'budget','revenue','profit','invoice'} else 'general'
        return {'format':ext[1:],'category':SUPPORTED[ext],'topic':topic,'chunks':chunks,'warnings':warnings,'classification':'deterministic format and keyword topic; not a semantic guarantee'}
    except HTTPException:raise
    except Exception:raise HTTPException(422,'File extraction failed; use a valid unencrypted file or local export')
