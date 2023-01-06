import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Stack, StackItem, CommandBarButton, IContextualMenuProps, IStackTokens } from '@fluentui/react';
// import TooltipHostForIcon from '@components/common/TooltipHostForIcon';
import WebRouters from './WebsiteRouter';
import TooltipHostForIcon from '@components/common/del/TooltipHostForIcon';
import LinksIcon from '@components/nav/LinksIcon';
import { MANAGER_IP, WEBUIDOC } from '@static/const';
import ExperimentSummaryPanel from './slideNav/ExperimentSummaryPanel';
import { EXPERIMENT } from '@static/datamodel';
import { getPrefix } from '@static/function';
import { SlideNavBtns } from './slideNav/SlideNavBtns';
import { timeIcon, disableUpdates, requency, closeTimer } from '@components/fluent/Icon';
import '@style/nav/nav.scss';
import '@style/icon.scss';
import { ErrorMessage } from '@components/nav/ErrorMessage';

const pageURLtoken: IStackTokens = {
    padding: '20px 10px',
    childrenGap: 8
};

const navMaintoken: IStackTokens = {
    childrenGap: 16
};

interface NavProps {
    changeInterval: (value: number) => void;
}

const NavCon = (props: NavProps): any => {
    const { changeInterval } = props;
    const [version, setVersion] = useState('999' as string);
    const [currentPage, setcurrentPage] = useState(
        window.location.pathname === '/oview' ? 'Overview' : 'Trials detail'
    );
    const [visibleExperimentPanel, setVisibleExperimentPanel] = useState(false);
    const [refreshText, setRefreshText] = useState('Auto refresh' as string);
    const [refreshFrequency, setRefreshFrequency] = useState(10 as number | string);

    const openGithub = (): void => {
        const feed = `https://github.com/Microsoft/nni/issues/new?labels=${version}`;
        window.open(feed);
    };

    const openDocs = (): void => {
        window.open(WEBUIDOC);
    };

    const openNNIcode = (): void => {
        // 999.0.0-developing
        let formatVersion = `v${version}`;
        if (version === '999.0.0-developing') {
            formatVersion = 'master';
        }
        window.open(`https://github.com/Microsoft/nni/tree/${formatVersion}`);
    };

    const getInterval = (num: number): void => {
        // 解开注释
        changeInterval(num); // notice parent component
        setRefreshFrequency(num === 0 ? '' : num);
        setRefreshText(num === 0 ? 'Disable auto' : 'Auto refresh');
    };

    useEffect(() => {
        axios(`${MANAGER_IP}/version`, {
            method: 'GET'
        })
            .then(res => {
                if (res.status === 200) {
                    let formatVersion = res.data;
                    // 2.0 will get 2.0.0 by node, so delete .0 to get real version
                    if (formatVersion.endsWith('.0')) {
                        formatVersion = formatVersion.slice(0, -2);
                    }
                    setVersion(formatVersion);
                }
            })
            .catch(_error => {
                // TODO 测试这块有没有问题，一个404的api返回status是200.。。
                setVersion('ERROR');
            });
    }, []);

    const refreshProps: IContextualMenuProps = {
        items: [
            {
                key: 'disableRefresh',
                text: 'Disable auto refresh',
                iconProps: closeTimer,
                onClick: getInterval.bind(this, 0)
            },
            {
                key: 'refresh10',
                text: 'Refresh every 10s',
                iconProps: requency,
                onClick: getInterval.bind(this, 10)
            },
            {
                key: 'refresh20',
                text: 'Refresh every 20s',
                iconProps: requency,
                onClick: getInterval.bind(this, 20)
            },
            {
                key: 'refresh30',
                text: 'Refresh every 30s',
                iconProps: requency,
                onClick: getInterval.bind(this, 30)
            },

            {
                key: 'refresh60',
                text: 'Refresh every 1min',
                iconProps: requency,
                onClick: getInterval.bind(this, 60)
            }
        ]
    };

    return (
        <React.Fragment>
            {/* shu */}
            <Stack className='nav-slider'>
                {/* TODO: add click event for Stack>div */}
                <Stack tokens={pageURLtoken}>
                    <img width='36' src={(getPrefix() || '') + '/icons/logo.png'} />
                    <WebRouters changeCurrentPage={setcurrentPage} />
                    {/* <TooltipHostForIcon tooltip='Overview' iconName='overview' pageURL='/oview'/>
                    <TooltipHostForIcon tooltip='Trials detail' iconName='detail' pageURL='/detail'/> */}
                    <TooltipHostForIcon tooltip='All experiments' iconName='all-experiments' pageURL='/experiment' />
                </Stack>
                <Stack tokens={pageURLtoken} className='bottom'>
                    <LinksIcon tooltip='Feedback' iconName='feedback' directional='right' iconClickEvent={openGithub} />
                    <LinksIcon tooltip='Document' iconName='document' directional='right' iconClickEvent={openDocs} />
                    <LinksIcon
                        tooltip={`Version: ${version}`}
                        iconName='version'
                        directional='right'
                        iconClickEvent={openNNIcode}
                    />
                </Stack>
            </Stack>
            {/* 横 */}
            <Stack horizontal horizontalAlign='space-between' className='nav-main'>
                <StackItem grow={30} className='title'>
                    {currentPage}
                </StackItem>
                <StackItem grow={70} className='options'>
                    <Stack horizontal horizontalAlign='end' tokens={navMaintoken}>
                        <LinksIcon
                            tooltip='Experiment summary'
                            iconName='summary'
                            directional='bottom'
                            iconClickEvent={(): void => setVisibleExperimentPanel(true)}
                        />
                        <div className='bar'>|</div>
                        <SlideNavBtns />
                        <div className='bar'>|</div>
                        <div className='nav-refresh'>
                            <CommandBarButton
                                iconProps={refreshFrequency === '' ? disableUpdates : timeIcon}
                                text={refreshText}
                                menuProps={refreshProps}
                            />
                            <div className='nav-refresh-num'>{refreshFrequency}</div>
                        </div>
                    </Stack>
                </StackItem>
            </Stack>
            {visibleExperimentPanel && (
                <ExperimentSummaryPanel
                    closeExpPanel={(): void => setVisibleExperimentPanel(false)}
                    experimentProfile={EXPERIMENT.profile}
                />
            )}
            {/* experiment error model */}
            <ErrorMessage />
        </React.Fragment>
    );
};

export default NavCon;
