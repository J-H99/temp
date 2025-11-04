#!/usr/bin/env python3
import os, sys, shlex, subprocess, statistics

USAGE = """\
Usage:
  python3 call_depth_rank.py <TARGET_FUNC> [SRC_ROOT='.'] [FILE_GLOB='*.c']
Example:
  python3 call_depth_rank.py parse_datetime ./ '*(.c|.h)'
"""

def run(cmd, cwd=None):
    return subprocess.run(
        cmd, cwd=cwd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True
    )
    # return subprocess.run(cmd, cwd=cwd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def list_functions(src_root, file_glob):
    # ctags로 함수 리스트 추출 (함수명만)
    # universal-ctags: c언어 함수: --c-kinds=f
    cmd = f"git -C {shlex.quote(src_root)} ls-files | grep -E '{file_glob}' || true"
    files = run(cmd).stdout.strip().splitlines()
    if not files:
        # git이 아닐 수도 있으니 find 백업
        cmd = f"find {shlex.quote(src_root)} -type f -name '*.c' -o -name '*.h'"
        files = run(cmd).stdout.strip().splitlines()
    if not files:
        return []
    # ctags 심볼 출력
    file_list = " ".join(shlex.quote(f) for f in files)
    cmd = f"ctags -x --c-kinds=f {file_list}"
    out = run(cmd).stdout
    funcs = []
    for line in out.splitlines():
        # 형식 예: name  function  file.c  /^...$/
        parts = line.split()
        if parts:
            funcs.append(parts[0])
    # 중복 제거
    return sorted(set(funcs))

def max_call_depth_for(func, src_root):
    # cflow는 들여쓰기로 트리 표현(기본 2칸). 첫 줄은 루트 자체이니 NR>1부터 계산.
    # 주: 거대한 프로젝트는 -I,-D 등 include가 필요할 수 있음. 필요시 수정.
    cmd = f"cflow --omit-arguments --main={shlex.quote(func)} $(git -C {shlex.quote(src_root)} ls-files '*.c' '*.h' 2>/dev/null || true)"
    p = run(cmd, cwd=src_root)
    text = p.stdout
    if not text.strip():
        return None
    maxdepth = 0
    for i, line in enumerate(text.splitlines(), 1):
        if i == 1:
            continue
        # 선행 공백 길이 구하고, 2칸=1레벨로 환산
        leading = len(line) - len(line.lstrip(' '))
        depth = leading // 2
        if depth > maxdepth:
            maxdepth = depth
    return maxdepth

def main():
    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(1)
    target = sys.argv[1]
    src_root = sys.argv[2] if len(sys.argv) >= 3 else "."
    file_glob = sys.argv[3] if len(sys.argv) >= 4 else r"\.c$|\.h$"

    funcs = list_functions(src_root, file_glob)
    if not funcs:
        print("함수를 찾지 못했습니다. ctags 설치/파일 확장자 확인 필요.")
        sys.exit(2)

    depths = []
    depth_map = {}
    for f in funcs:
        d = max_call_depth_for(f, src_root)
        if d is not None:
            depths.append(d)
            depth_map[f] = d

    if not depths:
        print("cflow 결과가 비었습니다. 컴파일 옵션(-I, -D) 문제일 수 있습니다.")
        sys.exit(3)

    depths.sort()
    # 대상 함수
    td = depth_map.get(target, None)
    if td is None:
        print(f"대상 함수 '{target}'의 호출 트리를 cflow가 만들지 못했습니다.")
        # 그래도 상위 20개 심도 있는 함수 출력
        top = sorted(depth_map.items(), key=lambda x: (-x[1], x[0]))[:20]
        print("\n[참고] 호출 심도 상위 20개:")
        for name, d in top:
            print(f"{d:>3}  {name}")
        sys.exit(4)

    # 퍼센타일/순위 계산
    import bisect
    rank = bisect.bisect_right(depths, td)
    pct = 100.0 * rank / len(depths)

    # 요약 출력
    print("=== 호출 그래프 깊이 결과 ===")
    print(f"대상 함수: {target}")
    print(f"최대 호출 깊이(depth): {td}")
    print(f"레포 내 상대 위치: 상위 {100-pct:.1f}% (퍼센타일 {pct:.1f}%)")
    print(f"함수 개수(측정가능): {len(depths)}")
    print()
    # 상/중/하 대략 기준
    q1 = depths[int(0.25*len(depths))]
    q2 = depths[int(0.50*len(depths))]
    q3 = depths[int(0.75*len(depths))]
    print(f"분위수: Q1={q1}, 중앙값={q2}, Q3={q3}")
    if td >= q3:
        print("해석: 호출 트리 기준으로 '깊은 편(상위 사분위)'입니다.")
    elif td <= q1:
        print("해석: 호출 트리 기준으로 '얕은 편(하위 사분위)'입니다.")
    else:
        print("해석: 호출 트리 기준으로 '중간 범위'입니다.")

    # 상위 20개 참고
    print("\n[참고] 호출 심도 상위 20개")
    top = sorted(depth_map.items(), key=lambda x: (-x[1], x[0]))[:20]
    for name, d in top:
        print(f"{d:>3}  {name}")

if __name__ == "__main__":
    main()
