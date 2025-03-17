#!/usr/bin/env python

from dlmonitor.sources.arxivsrc import ArxivSource

def test_search():
    # 测试向量搜索
    print("测试向量搜索: 'vision transformer'")
    results = ArxivSource().get_posts(keywords='vision transformer', num=5)
    print(f'搜索结果数量: {len(results)}')
    for i, paper in enumerate(results):
        print(f'{i+1}. {paper.title}')
    
    print("\n测试向量搜索: 'generative adversarial networks'")
    results = ArxivSource().get_posts(keywords='generative adversarial networks', num=5)
    print(f'搜索结果数量: {len(results)}')
    for i, paper in enumerate(results):
        print(f'{i+1}. {paper.title}')
    
    print("\n测试最新论文")
    results = ArxivSource().get_posts(keywords='fresh papers', num=5)
    print(f'搜索结果数量: {len(results)}')
    for i, paper in enumerate(results):
        print(f'{i+1}. {paper.title}')

if __name__ == "__main__":
    test_search() 