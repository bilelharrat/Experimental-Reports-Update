from server import news_archive


def test_discover_wechat_mmbiz_images_without_file_suffix():
    article_image = (
        "http://mmbiz.qpic.cn/mmbiz_jpg/example/0?wx_fmt=jpeg"
    )
    rendered_image = (
        "https://mmbiz.qpic.cn/sz_mmbiz_jpg/example/0"
        "?wxfrom=12&wx_fmt=jpg&usePicPrefetch=1"
    )
    html = f"""
    <html>
      <head>
        <meta property="og:image" content="{article_image}">
        <link as="script" href="https://res.wx.qq.com/assets/review_image.foo.js">
      </head>
      <body>
        <img src="{rendered_image}">
        <script>window.cgiData = {{ cdn_url: '{article_image}' }};</script>
      </body>
    </html>
    """

    discovery = news_archive._discover_asset_urls(html, "https://mp.weixin.qq.com/s/example")

    assert article_image in discovery["image_urls"]
    assert rendered_image in discovery["image_urls"]
    assert "https://res.wx.qq.com/assets/review_image.foo.js" not in discovery["image_urls"]


def test_wechat_download_candidates_try_https_and_trimmed_params():
    url = (
        "http://mmbiz.qpic.cn/mmbiz_jpg/example/0"
        "?wxfrom=12&wx_fmt=jpg&tp=webp&usePicPrefetch=1&watermark=1"
    )

    assert news_archive._download_candidates(url) == [
        url,
        (
            "https://mmbiz.qpic.cn/mmbiz_jpg/example/0"
            "?wxfrom=12&wx_fmt=jpg&tp=webp&usePicPrefetch=1&watermark=1"
        ),
        "http://mmbiz.qpic.cn/mmbiz_jpg/example/0?wx_fmt=jpg&tp=webp",
        "https://mmbiz.qpic.cn/mmbiz_jpg/example/0?wx_fmt=jpg&tp=webp",
    ]
