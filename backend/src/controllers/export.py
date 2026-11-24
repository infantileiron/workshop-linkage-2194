import csv
import io
from fastapi import HTTPException, Response


def safe(value):
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def export(item):
    if not item.result:
        raise HTTPException(409, '复核结果尚未完成')
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['复核单', '状态', '结论'])
    writer.writerow([safe(item.title), item.status, safe(item.result['summary'])])
    for key, value in item.result['metrics'].items():
        writer.writerow([key, value])
    rows = item.result['rows']
    if rows:
        writer.writerow([])
        writer.writerow(rows[0].keys())
        writer.writerows([safe(value) for value in row.values()] for row in rows)
    return Response(content='\ufeff' + stream.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="linkage-{item.id}.csv"'})


def export_experiment(report):
    """\u5bfc\u51fa\u63a8\u8350\u5b9e\u9a8c\u7684\u5bf9\u8d26\u62a5\u544a\uff08\u6309\u9996\u6b21\u8fdb\u7ec4\u9986\u5206\u5c42\u7684\u4e24\u7ec4\u8054\u62a5\u7387\uff09\u3002"""
    exp = report['experiment']
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['\u63a8\u8350\u5b9e\u9a8c', '\u72b6\u6001', '\u8bfe\u7a0b'])
    writer.writerow([safe(exp['title']), exp['state'], f"{exp['course_a']} \u00d7 {exp['course_b']}"])
    for key, value in report['metrics'].items():
        writer.writerow([key, value])
    rows = report['rows']
    if rows:
        writer.writerow([])
        writer.writerow(rows[0].keys())
        writer.writerows([safe(value) for value in row.values()] for row in rows)
        writer.writerow([])
        for note in report['notes']:
            writer.writerow([safe(note)])
    return Response(
        content='\ufeff' + stream.getvalue(), media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="experiment-{exp["id"]}.csv"'})
