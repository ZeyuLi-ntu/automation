"""Official SGD promotion adapters for the remaining institutions in the templates."""
from .common import load

BANKS={'BEA':'bea-sgd-promo','CITI':'citi-sgd-promo','HSBC':'hsbc-sgd-promo',
       'SingFinance':'singfinance-sgd-online','Singapura Finance':'singapura-sgd-promo','Maybank':'maybank-sgd-standalone'}

def configuration(bank,links='../利率链接.xlsx'):
    cfg=load('config/project.local.json');cfg['models'].update(num_ctx=32768,num_predict=8192)
    cfg.update(extraction_profile='multi-bank-literal-v1',transcribe_rate_units=True,expected_banks=[bank],products=[],sources=[],
       pdf_rate_products=[],pdf_rate_pages={},tenor_map={},pilot=dict(no_publication=True,scope=bank+' public SGD promotions; unavailable/app-only rates stay missing'))
    pid=BANKS[bank]
    def product(p,name):cfg['products'].append(dict(id=p,bank=bank,name=name,personal_status='unknown',expected=True))
    product(pid,bank+' SGD Fixed Deposit Promotion')
    def unit(selector,p=pid,kind='rates'):return dict(selector=selector,product_ids=[p],kind=kind)
    def source(key,url,units=None,p=pid,**extra):
        from urllib.parse import urlsplit
        if key in ['rates','counter','gold-bundle','private-bundle']:
            from .link_registry import bank_link
            origin=bank_link(links,bank,'SGD','促销',[urlsplit(url).hostname])
            # Registry may identify the institution's promotion directory.
            # The counter table lives on its dedicated fixed-deposit page.
            if not (bank=='Singapura Finance' and key=='counter' and urlsplit(origin['url']).path.rstrip('/')=='/promotions'):
                url=origin['url']
            cfg.setdefault('link_origins',[]).append(origin)
        s=dict(id=bank+'-'+key,bank=bank,enabled=True,urls=[url],domains=[urlsplit(url).hostname],max_depth=0,max_pages=1,product_ids=[p],settle_ms=2000,**extra)
        if units:s['capture_units']=units
        cfg['sources'].append(s)
    if bank=='BEA':
        source('rates','https://www.hkbea.com.sg/html/en/index.html',
            [unit('.swiper-slide:has(.banner-title:text-is("Enjoy a higher return with our Fixed Deposit promotion")) .content-block')],
            expand_selectors=['.swiper-pagination-bullet:nth-child(4)'])
        source('terms','https://www.hkbea.com.sg/pdf/sg/en/fd-terms-and-conditions.pdf')
    elif bank=='HSBC':
        source('rates','https://www.hsbc.com.sg/accounts/products/time-deposit/',
            [unit('#pp_tools_basicTable_'+str(i)) for i in range(1,5)]+[unit('#pp_tools_richtext_2',kind='terms')])
        source('terms','https://www.hsbc.com.sg/content/dam/hsbc/sg/documents/accounts/time-deposits/offers/sgd-terms-and-conditions.pdf')
    elif bank=='SingFinance':
        source('rates','https://www.singfinance.com.sg/fixed-deposit-fd-online/',
            [dict(**unit('table.pp-table'),table_grid=True),unit('.elementor-element:has(> .e-con-inner > .elementor-element-77ea46a)',kind='terms')])
    elif bank=='Singapura Finance':
        source('counter','https://www.singapurafinance.com.sg/promotions/fixed-deposit-promotion',
            [unit('section:has(table)'),unit('h1',kind='terms')])
        online='singapura-sgd-online';product(online,'Vivid Online Fixed Deposit Promotion')
        source('online','https://www.singapurafinance.com.sg/personal/accounts/vivid-fixed-deposit',
            [unit('#interest-rates',online),unit('#eligibility',online,'terms')],p=online)
    elif bank=='CITI':
        source('rates','https://www.citibank.com.sg/personal-banking/deposits/fixed-deposit-account',
            [dict(**unit('#text-0fb0879bbf table'),end_before='tr:has-text("USD")'),
             unit('.responsivegrid:has(> .title #title-8953c93628)',kind='terms')])
        for suffix,label,selector,tab in [('gold','Citigold','#text-eba8c0b51b .sgd','#tabs-c11cdc6863-item-896329dde6-tab'),('private','Citigold Private Client','#text-18b6b5dd09 .sgd','#tabs-c11cdc6863-item-f116fdc272-tab')]:
            bundle='citi-'+suffix+'-investment-bundle';product(bundle,label+' SGD Time Deposit Investment Bundle Promotion')
            source(suffix+'-bundle','https://www.citibank.com.sg/personal-banking/deposits/fixed-deposit-account',
                [unit(selector,bundle),unit(selector.split(' .sgd')[0],bundle,'terms')],p=bundle,expand_selectors=[tab])
    elif bank=='Maybank':
        from .link_registry import bank_link
        cfg['browser_channel']='chrome'
        cfg['products'][0]['name']='Maybank SGD Standalone Time Deposit Promotion'
        cfg['link_registry']=bank_link(links,'maybank','SGD','促销',['www.maybank2u.com.sg'])
        cfg['official_section_url']=cfg['link_registry']['url']
        cfg['scope_note']='User 2026-10-01 selected section ii Standalone Time Deposit; exclude Deposits Bundle Promotion.'
        section=dict(start=r'^ii\.\s*Standalone[^\n]*$',end=r'^How to place deposit$',
            context=r'^Singapore Dollar Time Deposit\s*/\s*Term Deposit-i\s*/\s*iSAVvy Time Deposit Promotion$',
            table_headers=['Tenure','Promotional Rates'],include_context_in_image=False)
        source('standalone',cfg['official_section_url'],[dict(**unit('body'),section_between=section)])
    return cfg
